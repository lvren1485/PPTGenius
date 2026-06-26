"""Knowledge ingestion & retrieval orchestrator — singleton.

Stores one BM25 index per scope (user:{id} or conv:{id}).  Built once at
explore-agent start, discarded when explore returns.
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
    """Ingest files, build BM25 index on demand, search (singleton)."""

    _instance: "KnowledgeService | None" = None

    def __new__(cls) -> "KnowledgeService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_init"):
            return
        self._init = True
        self._indexes: dict[str, BM25Manager] = {}  # "user:{id}" | "conv:{id}" → BM25

    # -- ingestion -----------------------------------------------------------

    async def ingest(self, db: Database, file_path: str | Path, user_id: int,
                     conversation_id: int | None = None,
                     source_type: str = "upload") -> int | None:
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
            user_id=user_id, filename=path.name, file_path=str(path),
            file_type=doc.file_type, file_size=path.stat().st_size,
            conversation_id=conversation_id, source_type=source_type,
        )
        chunks = chunk_text(doc.text)
        if not chunks:
            chunks = [doc.text]
        for idx, chunk_text_val in enumerate(chunks):
            await db.create_chunk(file_id=kf.id, chunk_index=idx, chunk_text=chunk_text_val)
        await db.update_knowledge_file_status(kf.id, "indexed", len(chunks))
        _log.info("ingested %s → %d chunks (file_id=%d)", path.name, len(chunks), kf.id)
        return kf.id

    # -- index lifecycle (called by explore agent) ---------------------------

    async def build_index(self, db: Database, *, user_id: int,
                          rag_mode: str, filter_web: bool,
                          conversation_id: int | None = None) -> str:
        """Build BM25 for *scope*.  Returns the scope key."""
        if rag_mode == "conversation" and conversation_id:
            chunks = await self._list_chunks(db, conversation_id=conversation_id,
                                              filter_web=filter_web)
            scope = f"conv:{conversation_id}"
        else:
            chunks = await self._list_chunks(db, user_id=user_id,
                                              filter_web=filter_web)
            scope = f"user:{user_id}"

        if not chunks:
            self._indexes.pop(scope, None)
            return ""

        bm = BM25Manager(Path(":memory:"), persist=False)
        bm.build(
            [c.chunk_text for c in chunks],
            meta=[{"chunk_id": c.id, "file_id": c.file_id} for c in chunks],
        )
        self._indexes[scope] = bm
        _log.info("index built: %s (%d chunks, filter_web=%s)", scope, len(chunks), filter_web)
        return scope

    def remove_index(self, scope: str = "") -> None:
        """Discard index for *scope*.  If empty, discard all indexes."""
        if scope:
            if self._indexes.pop(scope, None):
                _log.debug("index removed: %s", scope)
        else:
            self._indexes.clear()
            _log.debug("all indexes removed")

    # -- search --------------------------------------------------------------

    def _get_scope(self, *, rag_mode: str = "user", user_id: int = 0,
                   conversation_id: int | None = None) -> str:
        if rag_mode == "conversation" and conversation_id:
            return f"conv:{conversation_id}"
        return f"user:{user_id}"

    async def search(self, db: Database, user_id: int, query: str,
                     top_k: int = 5, filter_web: bool = False) -> list[dict]:
        scope = f"user:{user_id}"
        bm = self._indexes.get(scope)
        if bm is None:
            await self.build_index(db, user_id=user_id, rag_mode="user",
                                   filter_web=filter_web)
            bm = self._indexes.get(scope)
        if bm is None:
            return []
        return bm.search(query, top_k)

    async def search_by_conversation(
        self, db: Database, conversation_id: int, query: str,
        top_k: int = 5, filter_web: bool = False,
    ) -> list[dict]:
        scope = f"conv:{conversation_id}"
        bm = self._indexes.get(scope)
        if bm is None:
            await self.build_index(db, user_id=0, rag_mode="conversation",
                                   filter_web=filter_web,
                                   conversation_id=conversation_id)
            bm = self._indexes.get(scope)
        if bm is None:
            return []
        return bm.search(query, top_k)

    # -- file removal --------------------------------------------------------

    async def remove_file(self, db: Database, file_id: int) -> bool:
        kf = await db.get_knowledge_file(file_id)
        if kf is None:
            return False
        await db.delete_knowledge_file(file_id)
        _log.info("removed file_id=%d from user %d", file_id, kf.user_id)
        return True

    # -- internal ------------------------------------------------------------

    async def _list_chunks(self, db: Database, *, user_id: int = 0,
                           conversation_id: int | None = None,
                           filter_web: bool = False):
        if conversation_id:
            if filter_web:
                return await db.get_chunks_for_conversation_filter_web(conversation_id)
            return await db.get_all_chunks_for_conversation(conversation_id)
        if filter_web:
            return await db.get_chunks_for_user_filter_web(user_id)
        return await db.get_all_chunks_for_user(user_id)


knowledge_service = KnowledgeService()
