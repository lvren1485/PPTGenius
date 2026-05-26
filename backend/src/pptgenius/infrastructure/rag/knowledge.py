"""Knowledge ingestion & retrieval orchestrator — singleton.

Ties together: parser → chunker → BM25 → DB persistence.

One BM25 index per user, persisted as ``bm25_index_{user_id}.pkl``.
DB is passed per-method via the ``Database`` thin wrapper.
"""

from __future__ import annotations

from pathlib import Path

from pptgenius.infrastructure.config import get_settings
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
        self._indexes: dict[int, BM25Manager] = {}  # user_id → BM25Manager

    # -- ingestion -----------------------------------------------------------

    async def ingest(self, db: Database, file_path: str | Path, user_id: int) -> int | None:
        """Parse *file_path*, chunk it, persist chunks + rebuild index.

        Returns the ``KnowledgeFile.id``, or ``None`` on failure.
        """
        path = Path(file_path)
        if not path.exists():
            _log.error("file not found: %s", path)
            return None

        # 1. Parse
        try:
            doc = parse_file(path)
        except Exception:
            _log.exception("parse failed: %s", path)
            return None

        # 2. Create DB record
        kf = await db.create_knowledge_file(
            user_id=user_id,
            filename=path.name,
            file_path=str(path),
            file_type=doc.file_type,
            file_size=path.stat().st_size,
        )

        # 3. Chunk
        chunks = chunk_text(doc.text)
        if not chunks:
            _log.warning("no chunks produced for %s — treating as single chunk", path.name)
            chunks = [doc.text]

        # 4. Persist chunks to DB
        for idx, chunk_text_val in enumerate(chunks):
            await db.create_chunk(
                file_id=kf.id,
                chunk_index=idx,
                chunk_text=chunk_text_val,
            )

        await db.update_knowledge_file_status(kf.id, "indexed", len(chunks))

        # 5. Rebuild & save BM25 index for this user
        await self.rebuild_user_index(db, user_id)

        _log.info("ingested %s → %d chunks (file_id=%d)", path.name, len(chunks), kf.id)
        return kf.id

    # -- search --------------------------------------------------------------

    async def search(self, user_id: int, query: str, top_k: int = 5) -> list[dict]:
        """BM25 search across all chunks belonging to *user_id*."""
        bm = self._indexes.get(user_id)
        if bm is None:
            bm = self._get_bm25(user_id)
            if not bm.load():
                _log.debug("no index for user %d", user_id)
                return []
            self._indexes[user_id] = bm

        return bm.search(query, top_k)

    # -- index management ----------------------------------------------------

    async def rebuild_user_index(self, db: Database, user_id: int) -> None:
        """Rebuild the BM25 index for *user_id* from all DB chunks."""
        chunks = await db.get_all_chunks_for_user(user_id)
        bm = self._get_bm25(user_id)
        bm.build([c.chunk_text for c in chunks])
        bm.save()
        self._indexes[user_id] = bm
        _log.info("index rebuilt for user %d (%d chunks)", user_id, bm.chunk_count)

    async def remove_file(self, db: Database, file_id: int) -> bool:
        """Delete a knowledge file, its chunks, and rebuild the user index."""
        kf = await db.get_knowledge_file(file_id)
        if kf is None:
            return False
        user_id = kf.user_id
        await db.delete_knowledge_file(file_id)
        await self.rebuild_user_index(db, user_id)
        _log.info("removed file_id=%d from user %d", file_id, user_id)
        return True

    # -- internal ------------------------------------------------------------

    def _get_bm25(self, user_id: int) -> BM25Manager:
        cfg = get_settings().workspace
        index_dir = Path(cfg.root) / "indexes"
        index_dir.mkdir(parents=True, exist_ok=True)
        index_path = index_dir / f"bm25_index_{user_id}.pkl"
        return BM25Manager(index_path)


# Module-level convenience
knowledge_service = KnowledgeService()
