"""API router — registers all sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from .auth import router as auth_router
from .chat import router as chat_router
from .conversations import router as conversations_router
from .cost import router as cost_router
from .knowledge import router as knowledge_router
from .outline import router as outline_router
from .ppt import router as ppt_router
from .snapshot import router as snapshot_router
from .system import router as system_router
from .workspace import router as workspace_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(conversations_router)
api_router.include_router(chat_router)
api_router.include_router(outline_router)
api_router.include_router(ppt_router)
api_router.include_router(snapshot_router)
api_router.include_router(cost_router)
api_router.include_router(knowledge_router)
api_router.include_router(workspace_router)
api_router.include_router(system_router)
