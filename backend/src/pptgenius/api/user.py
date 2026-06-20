"""User settings API — web search, RAG mode, preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from pptgenius.infrastructure.db import Database

from .deps import get_db

router = APIRouter(prefix="/api/user", tags=["user"])


class UserSettings(BaseModel):
    web_search_enabled: bool = True
    rag_mode: str = "user"  # "user" | "conversation"


@router.get("/settings")
async def get_user_settings(
    request: Request,
    db: Database = Depends(get_db),
) -> dict:
    user_id = getattr(request.state, "user_id", 1)
    enabled = await db.get_web_search_enabled(user_id)
    mode = await db.get_rag_mode(user_id)
    return {"code": 0, "data": {"web_search_enabled": enabled, "rag_mode": mode}}


@router.put("/settings")
async def update_user_settings(
    settings: UserSettings,
    request: Request,
    db: Database = Depends(get_db),
) -> dict:
    user_id = getattr(request.state, "user_id", 1)
    if settings.rag_mode not in ("user", "conversation"):
        raise HTTPException(400, {"code": 40002, "message": "rag_mode must be 'user' or 'conversation'"})
    await db.set_web_search_enabled(user_id, settings.web_search_enabled)
    await db.set_rag_mode(user_id, settings.rag_mode)
    return {"code": 0, "data": {"web_search_enabled": settings.web_search_enabled, "rag_mode": settings.rag_mode}}
