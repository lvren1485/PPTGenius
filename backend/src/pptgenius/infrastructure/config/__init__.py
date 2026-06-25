"""Config — typed settings loaded from config.yaml + config.local.yaml.

Usage::

    from pptgenius.infrastructure.config import get_settings

    cfg = get_settings()
    print(cfg.llm.model)
"""

from .models import (
    AgentConfig,
    CacheConfig,
    DBConfig,
    LLMConfig,
    LogConfig,
    OutlineAgentConfig,
    RAGConfig,
    Settings,
    WebSearchConfig,
    WorkspaceConfig,
)
from .settings import RESOURCES_DIR, get_settings

__all__ = [
    "get_settings",
    "RESOURCES_DIR",
    "Settings",
    "WorkspaceConfig",
    "RAGConfig",
    "AgentConfig",
    "OutlineAgentConfig",
    "CacheConfig",
    "LLMConfig",
    "DBConfig",
    "LogConfig",
    "WebSearchConfig",
]
