"""Outline read-only endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from pptgenius.infrastructure.db import Database

from .deps import get_db
from .schemas import ApiResponse, OutlineBrief, OutlineDetail, OutlineSlideItem, PaginatedData

router = APIRouter(prefix="/api", tags=["outlines"])


def _orm_to_dict(obj) -> dict:
    d = dict(obj.__dict__)
    d.pop("_sa_instance_state", None)
    return d


@router.get("/outlines")
async def list_outlines(
    user_id: int = Query(..., description="User ID"),
    conversation_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
) -> ApiResponse[PaginatedData[OutlineBrief]]:
    if conversation_id is not None:
        items = await db.list_outlines_by_conversation(conversation_id)
    else:
        items = await db.list_outlines_by_user(user_id, offset=(page - 1) * page_size, limit=page_size)
    outlines = [OutlineBrief.model_validate(o) for o in items]
    return ApiResponse(data=PaginatedData(items=outlines, total=len(outlines), page=page, page_size=page_size))


@router.get("/outline/{outline_id}")
async def get_outline(
    outline_id: int,
    db: Database = Depends(get_db),
) -> ApiResponse[OutlineDetail]:
    outline = await db.get_outline(outline_id)
    if outline is None:
        raise HTTPException(404, {"code": 40001, "message": "outline not found"})
    slides = await db.get_slides_by_outline_id(outline_id)
    od = _orm_to_dict(outline)
    slide_items = []
    for s in slides:
        sd = _orm_to_dict(s)
        if isinstance(sd.get("content_json"), str):
            try:
                sd["content_json"] = json.loads(sd["content_json"])
            except (json.JSONDecodeError, TypeError):
                sd["content_json"] = {}
        slide_items.append(OutlineSlideItem(**sd))
    return ApiResponse(data=OutlineDetail(
        **od,
        slides=slide_items,
    ))


@router.get("/outline/{outline_id}/slides")
async def get_outline_slides(
    outline_id: int,
    db: Database = Depends(get_db),
) -> ApiResponse[list[OutlineSlideItem]]:
    outline = await db.get_outline(outline_id)
    if outline is None:
        raise HTTPException(404, {"code": 40001, "message": "outline not found"})
    slides = await db.get_slides_by_outline_id(outline_id)
    return ApiResponse(data=[OutlineSlideItem.model_validate(s) for s in slides])
