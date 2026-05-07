from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from rank_bm25 import BM25Okapi


def tokenize_for_bm25(text: str) -> List[str]:
    if not text.strip():
        return []
    return re.findall(r"[a-zA-Z]+|\d+|[\u4e00-\u9fff]", text.lower())


def chunk_text(text: str, max_chars: int = 280, overlap: int = 40) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


@dataclass(frozen=True)
class CorpusChunk:
    source_id: str
    text: str
    from_user: bool = False


class BM25Retriever:
    def __init__(self, chunks: Sequence[CorpusChunk]) -> None:
        self.chunks: List[CorpusChunk] = list(chunks)
        tokenized = [tokenize_for_bm25(c.text) for c in self.chunks]
        tokenized = [t if t else ["_"] for t in tokenized]
        self._bm25: Optional[BM25Okapi] = BM25Okapi(tokenized) if tokenized else None

    @classmethod
    def from_json_file(cls, path: Path) -> "BM25Retriever":
        raw = json.loads(path.read_text(encoding="utf-8"))
        chunks: List[CorpusChunk] = []
        for doc in raw:
            sid = str(doc.get("id") or doc.get("source_id") or "unknown")
            title = str(doc.get("title") or "").strip()
            body = str(doc.get("text") or "").strip()
            combined = (title + "\n" + body).strip() if title else body
            for piece in chunk_text(combined):
                chunks.append(CorpusChunk(source_id=sid, text=piece, from_user=False))
        return cls(chunks)

    @classmethod
    def from_text_documents(cls, docs: Iterable[tuple[str, str]]) -> "BM25Retriever":
        chunks: List[CorpusChunk] = []
        for source_id, text in docs:
            for piece in chunk_text(text, max_chars=420, overlap=72):
                chunks.append(CorpusChunk(source_id=source_id, text=piece, from_user=True))
        return cls(chunks)

    def retrieve(self, query: str, top_k: int = 6) -> List[CorpusChunk]:
        if not self.chunks or top_k <= 0 or self._bm25 is None:
            return []
        q_tokens = tokenize_for_bm25(query)
        if not q_tokens:
            q_tokens = ["_"]
        scores = self._bm25.get_scores(q_tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        pool_n = min(len(scores), max(top_k * 12, 28))
        pool = ranked[:pool_n]
        pool_sorted = sorted(pool, key=lambda i: (self.chunks[i].from_user, scores[i]), reverse=True)
        seen = set()
        out: List[CorpusChunk] = []
        for idx in pool_sorted:
            ch = self.chunks[idx]
            key = (ch.source_id, ch.text[:80])
            if key in seen:
                continue
            seen.add(key)
            out.append(ch)
            if len(out) >= top_k:
                break
        return out
