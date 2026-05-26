"""Conversation CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from pptgenius.infrastructure.db import Database

from .deps import get_db
from .schemas import (
    ApiResponse,
    ConversationBrief,
    ConversationDetail,
    CreateConversationRequest,
    MessageItem,
    OutlineBrief,
    PaginatedData,
    PresentationBrief,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", status_code=201)
async def create_conversation(
    req: CreateConversationRequest,
    db: Database = Depends(get_db),
) -> ApiResponse[ConversationBrief]:
    conv = await db.create_conversation(req.user_id, req.title)
    return ApiResponse(data=_conv_to_brief(conv, 0))


@router.get("")
async def list_conversations(
    user_id: int = Query(1),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
) -> ApiResponse[PaginatedData[ConversationBrief]]:
    convs = await db.list_conversations(user_id, status, offset=(page - 1) * page_size, limit=page_size)
    items = []
    for c in convs:
        count = await db.count_messages_by_conversation(c.id)
        items.append(_conv_to_brief(c, count))
    return ApiResponse(data=PaginatedData(items=items, total=len(items), page=page, page_size=page_size))


@router.get("/{conv_id}")
async def get_conversation(
    conv_id: int,
    db: Database = Depends(get_db),
) -> ApiResponse[ConversationDetail]:
    conv = await db.get_conversation(conv_id)
    if conv is None:
        raise HTTPException(404, {"code": 40001, "message": "conversation not found"})
    msgs = await db.get_messages_by_conversation(conv_id)
    outlines = await db.list_outlines_by_conversation(conv_id)
    presentations = await db.list_presentations_by_conversation(conv_id)
    return ApiResponse(data=ConversationDetail(
        id=conv.id,
        user_id=conv.user_id,
        title=conv.title,
        status=conv.status,
        current_phase=conv.current_phase,
        workspace_path=conv.workspace_path,
        estimated_cost=conv.estimated_cost,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[MessageItem.model_validate(m) for m in msgs],
        outlines=[OutlineBrief.model_validate(o) for o in outlines],
        presentations=[PresentationBrief.model_validate(p) for p in presentations],
    ))


@router.delete("/{conv_id}")
async def delete_conversation(
    conv_id: int,
    hard: bool = Query(False),
    db: Database = Depends(get_db),
) -> ApiResponse[dict]:
    conv = await db.get_conversation(conv_id)
    if conv is None:
        raise HTTPException(404, {"code": 40001, "message": "conversation not found"})
    if hard:
        # Hard delete not exposed on Database — just soft-delete for now
        # TODO: add hard_delete_conversation in repository if needed
        pass
    ok = await db.soft_delete_conversation(conv_id)
    return ApiResponse(data={"deleted": ok, "id": conv_id, "hard": hard})


# -- helpers ----------------------------------------------------------------


def _conv_to_brief(c, msg_count: int) -> ConversationBrief:
    return ConversationBrief(
        id=c.id,
        user_id=c.user_id,
        title=c.title,
        status=c.status,
        current_phase=c.current_phase,
        message_count=msg_count,
        estimated_cost=c.estimated_cost,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )
