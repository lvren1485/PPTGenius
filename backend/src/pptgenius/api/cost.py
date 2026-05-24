"""Cost statistics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from pptgenius.infrastructure.db.database import Database

from .deps import get_db
from .schemas import (
    ApiResponse,
    CostByConversationItem,
    CostByDateItem,
    CostSummaryData,
    PaginatedData,
)

router = APIRouter(prefix="/api/cost", tags=["cost"])


@router.get("/summary")
async def cost_summary(
    user_id: int = Query(..., description="User ID"),
    days: int = Query(30, ge=1, le=365),
    db: Database = Depends(get_db),
) -> ApiResponse[CostSummaryData]:
    data = await db.cost_summary(user_id, days)
    return ApiResponse(data=CostSummaryData(user_id=user_id, **data))


@router.get("/by-date")
async def cost_by_date(
    user_id: int = Query(..., description="User ID"),
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: Database = Depends(get_db),
) -> ApiResponse[PaginatedData[CostByDateItem]]:
    items = await db.cost_by_date(user_id, days, offset=(page - 1) * page_size, limit=page_size)
    return ApiResponse(data=PaginatedData(
        items=[CostByDateItem(**i) for i in items],
        total=days,
        page=page,
        page_size=page_size,
    ))


@router.get("/by-conversation")
async def cost_by_conversation(
    user_id: int = Query(..., description="User ID"),
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
) -> ApiResponse[PaginatedData[CostByConversationItem]]:
    items = await db.cost_by_conversation(user_id, days, offset=(page - 1) * page_size, limit=page_size)
    return ApiResponse(data=PaginatedData(
        items=[CostByConversationItem(**i) for i in items],
        total=len(items),
        page=page,
        page_size=page_size,
    ))
