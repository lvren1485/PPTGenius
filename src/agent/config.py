import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration loaded from environment variables."""

    # Paths
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
    RESOURCES_DIR: Path = PROJECT_ROOT / "resources"
    DATA_DIR: Path = PROJECT_ROOT / "data"
    VECTOR_DB_DIR: Path = DATA_DIR / "vector_db"
    SQLITE_DIR: Path = DATA_DIR / "sqlite"
    DB_PATH: Path = SQLITE_DIR / "agent.db"
    STRUCTURED_IMPORTS_DIR: Path = DATA_DIR / "structured_imports"
    OUTPUT_DIR: Path = PROJECT_ROOT / "output"
    LOG_DIR: Path = PROJECT_ROOT / "logs"
    CALLS_LOG_DIR: Path = LOG_DIR / "calls"
    SESSIONS_LOG_DIR: Path = LOG_DIR / "sessions"

    # LLM
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_MINI_MODEL: str = os.getenv("OPENAI_MINI_MODEL", "gpt-4o-mini")

    # Tech route switches
    EMBEDDER_BACKEND: str = os.getenv("EMBEDDER_BACKEND", "local")
    VECTOR_DB_BACKEND: str = os.getenv("VECTOR_DB_BACKEND", "chroma")

    # Embedding dimensions (depends on backend)
    @property
    def embedding_dimension(self) -> int:
        return 384 if self.EMBEDDER_BACKEND == "local" else 1536

    def ensure_dirs(self):
        """Create all required directories on startup."""
        for d in [
            self.RESOURCES_DIR, self.VECTOR_DB_DIR, self.SQLITE_DIR,
            self.STRUCTURED_IMPORTS_DIR, self.OUTPUT_DIR,
            self.CALLS_LOG_DIR, self.SESSIONS_LOG_DIR,
        ]:
            d.mkdir(parents=True, exist_ok=True)


config = Config()
