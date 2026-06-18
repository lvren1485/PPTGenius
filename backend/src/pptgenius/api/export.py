"""Export API — download outline (markdown) / presentation (pptx) from snapshots."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.export_service import export_service

from .deps import get_db

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export/outline/{snapshot_id}")
async def export_outline_md(
    snapshot_id: int,
    db: Database = Depends(get_db),
) -> FileResponse:
    """Export an outline snapshot as a markdown file."""
    try:
        filename, path = await export_service.export_outline_md(db, snapshot_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}")

    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/export/presentation/{snapshot_id}")
async def export_presentation_pptx(
    snapshot_id: int,
    db: Database = Depends(get_db),
) -> FileResponse:
    """Export a presentation snapshot as a .pptx file."""
    try:
        filename, path = await export_service.export_presentation_pptx(db, snapshot_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}")

    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
