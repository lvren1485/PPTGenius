"""Workspace status endpoint."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from pptgenius.infrastructure.config.settings import get_settings
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.workspace.manager import WorkspaceManager

from .deps import get_db, get_workspace_manager
from .schemas import (
    ApiResponse,
    BM25IndexInfo,
    BM25Status,
    WorkspaceConvStatus,
    WorkspaceStatusData,
)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _count_files(path: Path) -> dict[str, int]:
    counts = {}
    if path.exists():
        for child in path.iterdir():
            if child.is_dir():
                counts[child.name] = sum(1 for _ in child.rglob("*") if _.is_file())
    return counts


def _format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@router.get("/status")
async def workspace_status(
    user_id: int = Query(..., description="User ID"),
    db: Database = Depends(get_db),
    wm: WorkspaceManager = Depends(get_workspace_manager),
) -> ApiResponse[WorkspaceStatusData]:
    ws_root = Path(get_settings().workspace.root)

    # Per-conversation directories
    convs = await db.list_conversations(user_id)
    conv_statuses = []
    for c in convs:
        base = wm.get_path(c.id)
        conv_statuses.append(WorkspaceConvStatus(
            conversation_id=c.id,
            disk_usage=_format_size(_dir_size(base)),
            file_counts=_count_files(base),
        ))

    # BM25 indexes
    index_dir = ws_root / "indexes"
    indexes = []
    if index_dir.exists():
        for pkl in sorted(index_dir.glob("bm25_index_*.pkl")):
            uid = int(pkl.stem.rsplit("_", 1)[-1])
            idx_size = pkl.stat().st_size
            indexes.append(BM25IndexInfo(
                user_id=uid,
                file=pkl.name,
                chunk_count=0,  # would need to load pickle to get real count
            ))

    return ApiResponse(data=WorkspaceStatusData(
        workspace_root=str(ws_root.resolve()),
        conversations=conv_statuses,
        bm25_index=BM25Status(
            index_dir=str(index_dir.resolve()) if index_dir.exists() else str(index_dir),
            indexes=indexes,
        ),
    ))
