import json
import math
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import config


class VectorStore(ABC):
    """Abstract interface for vector storage and similarity search."""

    @abstractmethod
    def add_texts(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict] | None = None,
    ):
        ...

    @abstractmethod
    def similarity_search(
        self, query: str, k: int = 5
    ) -> list[tuple[str, float, dict]]:
        """Returns (text, score, metadata) tuples."""
        ...

    def persist(self):
        pass


class JSONVectorStore(VectorStore):
    """Zero-dependency vector store using JSON file + numpy cosine similarity."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or config.VECTOR_DB_DIR / "vectors.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict] = []
        self._load()

    def _load(self):
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self.entries = json.load(f)

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False)

    def add_texts(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict] | None = None,
    ):
        from .embedder import create_embedder
        embedder = create_embedder()
        embeddings = embedder.embed(texts)
        for i, (tid, text) in enumerate(zip(ids, texts)):
            self.entries.append({
                "id": tid,
                "text": text,
                "embedding": embeddings[i],
                "metadata": metadatas[i] if metadatas else {},
            })
        self._save()

    def similarity_search(
        self, query: str, k: int = 5
    ) -> list[tuple[str, float, dict]]:
        if not self.entries:
            return []

        from .embedder import create_embedder
        embedder = create_embedder()
        query_emb = embedder.embed([query])[0]

        scored = []
        for entry in self.entries:
            score = self._cosine_sim(query_emb, entry["embedding"])
            scored.append((score, entry["text"], entry["metadata"]))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [(text, score, meta) for score, text, meta in scored[:k]]

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0


def create_vector_store() -> VectorStore:
    """Factory: create vector store based on config."""
    backend = config.VECTOR_DB_BACKEND
    if backend == "chroma":
        try:
            import chromadb
            client = chromadb.PersistentClient(str(config.VECTOR_DB_DIR))
            collection = client.get_or_create_collection("documents")
            return _ChromaWrapper(collection)
        except ImportError:
            pass
    return JSONVectorStore()


class _ChromaWrapper(VectorStore):
    """Adapter wrapping a ChromaDB collection as a VectorStore."""

    def __init__(self, collection):
        self.collection = collection

    def add_texts(self, ids, texts, metadatas=None):
        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas or [{}] * len(texts),
        )

    def similarity_search(self, query, k=5):
        results = self.collection.query(query_texts=[query], n_results=k)
        out = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                score = results["distances"][0][i] if results["distances"] else 0
                out.append((doc, 1.0 - score, meta))
        return out
