"""Per-conversation workspace directory management — singleton."""

from __future__ import annotations

import shutil
from pathlib import Path

from pptgenius.infrastructure.config.settings import get_settings
from pptgenius.infrastructure.utils.logger import get_logger

_log = get_logger("pptgenius.workspace")


class WorkspaceManager:
    """Manage per-conversation workspace directories (singleton).

    Layout::

        {root}/
        └── {conversation_id}/
            ├── input/        # uploaded source files
            ├── knowledge/    # parsed + chunked knowledge
            └── output/       # generated .pptx files
    """

    _instance: "WorkspaceManager | None" = None

    def __new__(cls, root: str | Path | None = None) -> "WorkspaceManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, root: str | Path | None = None) -> None:
        if hasattr(self, "_initialised"):
            return
        self._initialised = True
        cfg = get_settings().workspace
        self.root = Path(root) if root else Path(cfg.root)
        self.input_dir = cfg.input_dir
        self.knowledge_dir = cfg.knowledge_dir
        self.output_dir = cfg.output_dir

    # -- public API ----------------------------------------------------------

    def create(self, conversation_id: int) -> Path:
        """Create workspace directories for *conversation_id*. Returns the base path."""
        base = self._path(conversation_id)
        (base / self.input_dir).mkdir(parents=True, exist_ok=True)
        (base / self.knowledge_dir).mkdir(parents=True, exist_ok=True)
        (base / self.output_dir).mkdir(parents=True, exist_ok=True)
        _log.debug("workspace created: %s", base)
        return base

    def clean(self, conversation_id: int) -> None:
        """Remove the entire workspace for *conversation_id*."""
        base = self._path(conversation_id)
        if base.exists():
            shutil.rmtree(base)
            _log.debug("workspace cleaned: %s", base)

    def get_input_dir(self, conversation_id: int) -> Path:
        return self._path(conversation_id) / self.input_dir

    def get_knowledge_dir(self, conversation_id: int) -> Path:
        return self._path(conversation_id) / self.knowledge_dir

    def get_output_dir(self, conversation_id: int) -> Path:
        return self._path(conversation_id) / self.output_dir

    def get_path(self, conversation_id: int) -> Path:
        return self._path(conversation_id)

    # -- internal ------------------------------------------------------------

    def _path(self, conversation_id: int) -> Path:
        return self.root / str(conversation_id)
