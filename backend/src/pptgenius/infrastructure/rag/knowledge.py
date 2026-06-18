"""Knowledge ingestion & retrieval orchestrator — singleton.

Ties together: parser → chunker → BM25 → DB persistence.

Indexing strategy:
  - Indexes are built ONCE at chat-start via ``ensure_index()``.
  - Ingest / remove only mark a dirty flag (``users.other.rag_index_changed``).
  - Within a chat turn, the cached index is reused until the LLM calls the
    ``rebuild_rag_index`` tool (or the next chat turn rebuilds it).
  - Conversation-level indexes are always dynamic (built on first search).
"""

from __future__ import annotations

from pathlib import Path

from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

from .bm25 import BM25Manager
from .chunker import chunk_text
from .parser import parse_file

_log = get_logger("pptgenius.knowledge")


class KnowledgeService:
    """Ingest files, build BM25 index, search (singleton)."""

    _instance: "KnowledgeService | None" = None

    def __new__(cls) -> "KnowledgeService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialised"):
            return
        self._initialised = True
        self._user_indexes: dict[int, BM25Manager] = {}     # user_id → in-memory BM25
        self._conv_indexes: dict[int, BM25Manager] = {}      # conversation_id → in-memory BM25

    # -- ingestion -----------------------------------------------------------

    async def ingest(self, db: Database, file_path: str | Path, user_id: int,
                     conversation_id: int | None = None,
                     source_type: str = "upload") -> int | None:
        """Parse *file_path*, chunk, persist.  Marks index dirty."""
        path = Path(file_path)
        if not path.exists():
            _log.error("file not found: %s", path)
            return None

        try:
            doc = parse_file(path)
        except Exception:
            _log.exception("parse failed: %s", path)
            return None

        kf = await db.create_knowledge_file(
            user_id=user_id,
            filename=path.name,
            file_path=str(path),
            file_type=doc.file_type,
            file_size=path.stat().st_size,
            conversation_id=conversation_id,
            source_type=source_type,
        )

        chunks = chunk_text(doc.text)
        if not chunks:
            chunks = [doc.text]

        for idx, chunk_text_val in enumerate(chunks):
            await db.create_chunk(file_id=kf.id, chunk_index=idx, chunk_text=chunk_text_val)

        await db.update_knowledge_file_status(kf.id, "indexed", len(chunks))

        # Mark dirty — next ensure_index() will rebuild
        await db.set_rag_index_changed(user_id)
        self._user_indexes.pop(user_id, None)
        self._conv_indexes.pop(conversation_id, None)

        _log.info("ingested %s → %d chunks (file_id=%d)", path.name, len(chunks), kf.id)
        return kf.id

    # -- ensure index (called once at chat start) ---------------------------

    async def ensure_index(self, db: Database, *, user_id: int,
                           rag_mode: str, filter_web: bool,
                           conversation_id: int | None = None) -> None:
        """Ensure a fresh BM25 index is ready for this chat turn.

        Called once at chat entry.  Rebuilds if the dirty flag is set or
        no cached index exists.
        """
        if rag_mode == "conversation" and conversation_id:
            if conversation_id in self._conv_indexes:
                return
            bm = await self._build_conv_index(db, conversation_id, filter_web=filter_web)
            if bm:
                self._conv_indexes[conversation_id] = bm
            return

        # user mode
        changed = await db.is_rag_index_changed(user_id)
        if not changed and user_id in self._user_indexes:
            return  # cached index still fresh

        bm = await self._build_user_index(db, user_id, filter_web=filter_web)
        if bm:
            self._user_indexes[user_id] = bm
        await db.clear_rag_index_changed(user_id)
        _log.info("ensure_index user=%d mode=%s filter_web=%s built=%s",
                   user_id, rag_mode, filter_web, bm is not None)

    # -- search (user-level) ------------------------------------------------

    async def search(self, db: Database, user_id: int, query: str,
                     top_k: int = 5, filter_web: bool = False) -> list[dict]:
        """BM25 search across user chunks.  Uses cached index; no auto-rebuild."""
        bm = self._user_indexes.get(user_id)
        if bm is None:
            _log.warning("no cached index for user %d — building on demand", user_id)
            bm = await self._build_user_index(db, user_id, filter_web=filter_web)
            if bm is None:
                return []
            self._user_indexes[user_id] = bm
        return bm.search(query, top_k)

    async def _build_user_index(self, db: Database, user_id: int,
                                 filter_web: bool = False) -> BM25Manager | None:
        if filter_web:
            chunks = await db.get_chunks_for_user_filter_web(user_id)
        else:
            chunks = await db.get_all_chunks_for_user(user_id)
        if not chunks:
            return None
        bm = BM25Manager(Path(":memory:"), persist=False)
        bm.build([c.chunk_text for c in chunks])
        _log.debug("built user index for %d (%d chunks, filter_web=%s)",
                    user_id, len(chunks), filter_web)
        return bm

    # -- search (conversation-level) ----------------------------------------

    async def search_by_conversation(
        self, db: Database, conversation_id: int, query: str,
        top_k: int = 5, filter_web: bool = False,
    ) -> list[dict]:
        """BM25 search within a conversation.  Builds on first access."""
        bm = self._conv_indexes.get(conversation_id)
        if bm is None:
            bm = await self._build_conv_index(db, conversation_id, filter_web=filter_web)
            if bm is None:
                return []
            self._conv_indexes[conversation_id] = bm
        return bm.search(query, top_k)

    async def _build_conv_index(
        self, db: Database, conversation_id: int, filter_web: bool = False,
    ) -> BM25Manager | None:
        if filter_web:
            chunks = await db.get_chunks_for_conversation_filter_web(conversation_id)
        else:
            chunks = await db.get_all_chunks_for_conversation(conversation_id)
        if not chunks:
            return None
        bm = BM25Manager(Path(":memory:"), persist=False)
        bm.build([c.chunk_text for c in chunks])
        _log.debug("built conv index for %d (%d chunks, filter_web=%s)",
                    conversation_id, len(chunks), filter_web)
        return bm

    async def rebuild_conversation_index(
        self, db: Database, conversation_id: int, filter_web: bool = False,
    ) -> None:
        bm = await self._build_conv_index(db, conversation_id, filter_web=filter_web)
        if bm is not None:
            self._conv_indexes[conversation_id] = bm
        elif conversation_id in self._conv_indexes:
            del self._conv_indexes[conversation_id]

    def remove_conversation_index(self, conversation_id: int) -> None:
        self._conv_indexes.pop(conversation_id, None)

    # -- file removal --------------------------------------------------------

    async def remove_file(self, db: Database, file_id: int) -> bool:
        kf = await db.get_knowledge_file(file_id)
        if kf is None:
            return False
        await db.delete_knowledge_file(file_id)
        await db.set_rag_index_changed(kf.user_id)
        self._user_indexes.pop(kf.user_id, None)
        if kf.conversation_id:
            self._conv_indexes.pop(kf.conversation_id, None)
        _log.info("removed file_id=%d from user %d", file_id, kf.user_id)
        return True


knowledge_service = KnowledgeService()
