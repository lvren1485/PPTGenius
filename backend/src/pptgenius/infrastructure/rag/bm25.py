"""BM25 index wrapper with pickle persistence.

One index per user (keyed by user_id).  All parsed + chunked knowledge
files belonging to a user are indexed together.
"""

from __future__ import annotations

import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi

from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.bm25")


class BM25Manager:
    """Build / persist / query a BM25 index for one user.

    When *persist* is False, ``save()`` and ``load()`` are no-ops — used
    for dynamic in-memory conversation-level indexes.
    """

    def __init__(self, index_path: str | Path, persist: bool = True) -> None:
        self.index_path = Path(index_path)
        self.persist = persist
        self._index: BM25Okapi | None = None
        self._chunks: list[str] = []  # corpus, mirrors index order

    # -- build ---------------------------------------------------------------

    def build(self, chunks: list[str]) -> None:
        """Build a new index from *chunks* (replaces current)."""
        if not chunks:
            _log.warning("build called with empty chunk list — index cleared")
            self._index = None
            self._chunks = []
            return
        tokenized = [self._tokenize(c) for c in chunks]
        self._index = BM25Okapi(tokenized)
        self._chunks = chunks
        _log.debug("index built: %d documents", len(chunks))

    def add(self, chunks: list[str]) -> None:
        """Rebuild index with current + new chunks."""
        all_chunks = self._chunks + chunks
        self.build(all_chunks)

    def remove(self, predicate) -> int:
        """Remove chunks matching *predicate* (callable). Returns count removed."""
        before = len(self._chunks)
        self._chunks = [c for c in self._chunks if not predicate(c)]
        removed = before - len(self._chunks)
        if removed:
            self.build(self._chunks)
        return removed

    # -- query ---------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return top-k results as ``[{chunk, score}, ...]``."""
        if self._index is None:
            return []
        tokens = self._tokenize(query)
        scores = self._index.get_scores(tokens)
        # Get top-k indices
        ranked = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]
        return [
            {"chunk": self._chunks[i], "score": round(float(scores[i]), 4)}
            for i in ranked
        ]

    # -- persistence ---------------------------------------------------------

    def save(self) -> None:
        """Pickle the BM25Okapi object + chunks to disk."""
        if not self.persist:
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"index": self._index, "chunks": self._chunks}
        with open(self.index_path, "wb") as f:
            pickle.dump(data, f)
        _log.debug("index saved → %s (%d docs)", self.index_path, len(self._chunks))

    def load(self) -> bool:
        """Load pickled index. Returns False if file missing or not persisted."""
        if not self.persist:
            return False
        if not self.index_path.exists():
            _log.debug("index file not found: %s", self.index_path)
            return False
        with open(self.index_path, "rb") as f:
            data = pickle.load(f)
        self._index = data["index"]
        self._chunks = data["chunks"]
        _log.debug("index loaded ← %s (%d docs)", self.index_path, len(self._chunks))
        return True

    # -- properties ----------------------------------------------------------

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    # -- internal ------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize with jieba for Chinese + English mixed text."""
        try:
            import jieba
            return [t.lower() for t in jieba.cut(text) if t.strip()]
        except ImportError:
            return text.lower().split()
