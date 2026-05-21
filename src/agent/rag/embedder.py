from abc import ABC, abstractmethod
from ..config import config


class Embedder(ABC):
    """Abstract interface for text embedding."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...


class LocalEmbedder(Embedder):
    """Local embedding via sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        # Eager check: fail fast if package missing
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: uv add sentence-transformers"
            )

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: uv add sentence-transformers"
                )

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load()
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        self._load()
        return self._model.get_sentence_embedding_dimension()


class OpenAIEmbedder(Embedder):
    """Embedding via OpenAI API."""

    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self._client = None

    def _load(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=config.OPENAI_API_KEY)

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load()
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]

    @property
    def dimension(self) -> int:
        if "3-small" in self.model:
            return 1536
        return 3072


def create_embedder() -> Embedder:
    """Factory: create embedder based on config."""
    backend = config.EMBEDDER_BACKEND
    if backend == "openai":
        return OpenAIEmbedder()
    else:
        try:
            return LocalEmbedder()
        except ImportError:
            # Fallback to a simple mock
            class _MockEmbedder(Embedder):
                def embed(self, texts: list[str]) -> list[list[float]]:
                    return [[0.0] * self.dimension for _ in texts]
                @property
                def dimension(self) -> int:
                    return 384
            return _MockEmbedder()
