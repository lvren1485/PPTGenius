"""FastAPI dependency injection — registers all singleton services.

Usage in routes::

    from pptgenius.api.deps import Database, KnowledgeManager, WorkspaceManager

    @router.post("/ingest")
    async def ingest(
        db: Database = Depends(get_db),
        km: KnowledgeManager = Depends(get_knowledge_manager),
        wm: WorkspaceManager = Depends(get_workspace_manager),
    ): ...
"""

from __future__ import annotations

from typing import AsyncGenerator

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.db.engine import get_db as _get_db_session
from pptgenius.infrastructure.rag.knowledge import (
    KnowledgeService,
    knowledge_service,
)
from pptgenius.infrastructure.rag.web_search import WebSearchService, web_search_service
from pptgenius.infrastructure.workspace.manager import WorkspaceManager


# -- DB ----------------------------------------------------------------------

async def get_db() -> AsyncGenerator[Database, None]:
    """Yield a Database wrapper per request, auto-closed after."""
    async for session in _get_db_session():
        yield Database(session)


# -- singleton services ------------------------------------------------------

def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


def get_knowledge_manager() -> KnowledgeService:
    return knowledge_service


def get_web_search_service() -> WebSearchService:
    return web_search_service


__all__ = [
    "Database",
    "KnowledgeService",
    "WebSearchService",
    "WorkspaceManager",
    "get_db",
    "get_knowledge_manager",
    "get_web_search_service",
    "get_workspace_manager",
]
