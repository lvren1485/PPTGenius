"""Snapshot read-only endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pptgenius.infrastructure.db.database import Database

from .deps import get_db
from .schemas import ApiResponse, SnapshotBrief, SnapshotDetail

router = APIRouter(prefix="/api", tags=["snapshots"])


@router.get("/ppt/{pres_id}/snapshots")
async def list_snapshots(
    pres_id: int,
    db: Database = Depends(get_db),
) -> ApiResponse[dict]:
    pres = await db.get_presentation(pres_id)
    if pres is None:
        raise HTTPException(404, {"code": 40001, "message": "presentation not found"})
    snaps = await db.list_snapshots_by_presentation(pres_id)
    return ApiResponse(data={
        "presentation_id": pres_id,
        "snapshots": [SnapshotBrief.model_validate(s) for s in snaps],
    })


@router.get("/snapshots/{snap_id}")
async def get_snapshot(
    snap_id: int,
    db: Database = Depends(get_db),
) -> ApiResponse[SnapshotDetail]:
    snap = await db.get_snapshot(snap_id)
    if snap is None:
        raise HTTPException(404, {"code": 40001, "message": "snapshot not found"})
    return ApiResponse(data=SnapshotDetail.model_validate(snap))
