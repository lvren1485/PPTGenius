"""PPT read-only endpoints + download."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from pptgenius.infrastructure.db.database import Database

from .deps import get_db
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
    pres_list = [PresentationBrief.model_validate(p) for p in items]
    return ApiResponse(data=PaginatedData(items=pres_list, total=len(pres_list), page=page, page_size=page_size))


@router.get("/ppt/{pres_id}")
async def get_presentation(
    pres_id: int,
    db: Database = Depends(get_db),
) -> ApiResponse[PresentationDetail]:
    pres = await db.get_presentation(pres_id)
    if pres is None:
        raise HTTPException(404, {"code": 40001, "message": "presentation not found"})
    return ApiResponse(data=PresentationDetail.model_validate(pres))


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
        slides=[PresentationSlideDetail.model_validate(s) for s in slides],
    ))


@router.get("/ppt/{pres_id}/download")
async def download_presentation(
    pres_id: int,
    db: Database = Depends(get_db),
) -> FileResponse:
    pres = await db.get_presentation(pres_id)
    if pres is None:
        raise HTTPException(404, {"code": 40001, "message": "presentation not found"})
    if pres.status != "completed" or not pres.file_path:
        raise HTTPException(400, {"code": 40401, "message": "presentation not ready for download"})
    if not os.path.isfile(pres.file_path):
        raise HTTPException(404, {"code": 40402, "message": "file not found on disk"})

    filename = os.path.basename(pres.file_path)
    return FileResponse(
        path=pres.file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
