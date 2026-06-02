"""PPT read-only endpoints + download."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from pptgenius.infrastructure.db import Database

from .deps import get_db, get_workspace_manager


def _orm_to_dict(obj) -> dict:
    """Extract ORM column values — uses __dict__ for speed, permissive about
    server-generated columns that may not be present."""
    d = dict(obj.__dict__)
    d.pop("_sa_instance_state", None)
    return d
from .schemas import (
    ApiResponse,
    PaginatedData,
    PresentationBrief,
    PresentationDetail,
    PresentationSlideDetail,
    PresentationSlidesResponse,
)

router = APIRouter(prefix="/api", tags=["presentations"])


@router.get("/presentations")
async def list_presentations(
    user_id: int = Query(..., description="User ID"),
    conversation_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
) -> ApiResponse[PaginatedData[PresentationBrief]]:
    if conversation_id is not None:
        items = await db.list_presentations_by_conversation(conversation_id)
    else:
        items = await db.list_presentations_by_user(user_id, offset=(page - 1) * page_size, limit=page_size)
    pres_list = [PresentationBrief(**_orm_to_dict(p)) for p in items]
    return ApiResponse(data=PaginatedData(items=pres_list, total=len(pres_list), page=page, page_size=page_size))


@router.get("/ppt/{pres_id}")
async def get_presentation(
    pres_id: int,
    db: Database = Depends(get_db),
) -> ApiResponse[PresentationDetail]:
    pres = await db.get_presentation(pres_id)
    if pres is None:
        raise HTTPException(404, {"code": 40001, "message": "presentation not found"})

    data = _orm_to_dict(pres)

    # Resolve template / color_scheme names
    if pres.template_id:
        tpl = await db.get_template(pres.template_id)
        data["template_name"] = tpl.label if tpl else None
    else:
        data["template_name"] = None

    if pres.color_scheme_id:
        cs = await db.get_color_scheme(pres.color_scheme_id)
        data["color_scheme_name"] = cs.label if cs else None
    else:
        data["color_scheme_name"] = None

    return ApiResponse(data=PresentationDetail(**data))


@router.get("/ppt/{pres_id}/slides")
async def get_presentation_slides(
    pres_id: int,
    db: Database = Depends(get_db),
) -> ApiResponse[PresentationSlidesResponse]:
    pres = await db.get_presentation(pres_id)
    if pres is None:
        raise HTTPException(404, {"code": 40001, "message": "presentation not found"})
    slides = await db.get_slides_by_presentation_id(pres_id)
    return ApiResponse(data=PresentationSlidesResponse(
        presentation_id=pres_id,
        slides=[PresentationSlideDetail(**_orm_to_dict(s)) for s in slides],
    ))


@router.get("/ppt/{pres_id}/download")
async def download_presentation(
    pres_id: int,
    db: Database = Depends(get_db),
    wm = Depends(get_workspace_manager),
) -> FileResponse:
    pres = await db.get_presentation(pres_id)
    if pres is None:
        raise HTTPException(404, {"code": 40001, "message": "presentation not found"})
    if pres.status != "completed" or not pres.file_path:
        raise HTTPException(400, {"code": 40401, "message": "presentation not ready for download"})

    # Resolve file path — try stored path first, then output dir by naming convention
    file_path = pres.file_path
    if not os.path.isabs(file_path):
        file_path = os.path.join(str(wm.get_path(pres.conversation_id)), file_path)

    # Fallback: look for {pres_id}.pptx in output dir
    if not os.path.isfile(file_path):
        output_dir = wm.get_output_dir(pres.conversation_id)
        fallback = os.path.join(str(output_dir), f"{pres_id}.pptx")
        if os.path.isfile(fallback):
            file_path = fallback

    if not os.path.isfile(file_path):
        raise HTTPException(404, {"code": 40402, "message": f"file not found: {os.path.basename(file_path)}"})

    filename = os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
