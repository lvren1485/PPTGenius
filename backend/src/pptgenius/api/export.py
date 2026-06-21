"""Export API — download outline (markdown) / presentation (pptx) from snapshots.
Also provides content endpoints that return data in-memory for preview before download."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.export_service import export_service

from .deps import get_db

router = APIRouter(prefix="/api", tags=["export"])


# ── Snapshot listing ───────────────────────────────────────────────────


@router.get("/export/outline-snapshots/{outline_id}")
async def list_outline_snapshots(
    outline_id: int,
    db: Database = Depends(get_db),
) -> dict:
    """List snapshots for an outline."""
    snaps = await db.list_outline_snapshots(outline_id)
    return {
        "code": 0,
        "data": {
            "outline_id": outline_id,
            "snapshots": [{"id": s.id, "version": s.version, "created_at": s.created_at.isoformat()} for s in snaps],
        },
    }


# ── Content endpoints (preview before download) ──────────────────────────


@router.get("/export/outline/{snapshot_id}/content")
async def get_outline_content(
    snapshot_id: int,
    db: Database = Depends(get_db),
) -> dict:
    """Return outline markdown content for preview."""
    try:
        filename, path = await export_service.export_outline_md(db, snapshot_id)
        content = path.read_text(encoding="utf-8")
        return {"code": 0, "data": {"filename": filename, "content": content}}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"导出失败: {e}")


@router.get("/export/presentation/{snapshot_id}/content")
async def get_presentation_content(
    snapshot_id: int,
    db: Database = Depends(get_db),
) -> dict:
    """Return presentation pptx as base64 for preview."""
    try:
        filename, path = await export_service.export_presentation_pptx(db, snapshot_id)
        content_bytes = path.read_bytes()
        content_b64 = base64.b64encode(content_bytes).decode("ascii")
        return {"code": 0, "data": {"filename": filename, "content": content_b64}}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"导出失败: {e}")


# ── Direct download endpoints (legacy) ───────────────────────────────────


@router.get("/export/outline/{snapshot_id}")
async def export_outline_md(
    snapshot_id: int,
    db: Database = Depends(get_db),
) -> FileResponse:
    """Export an outline snapshot as a markdown file (direct download)."""
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
    """Export a presentation snapshot as a .pptx file (direct download)."""
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
