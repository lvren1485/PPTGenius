"""Knowledge file management endpoints.

BM25 retrieval is internal to the agent — not exposed via HTTP.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.rag import KnowledgeService
from pptgenius.infrastructure.utils import get_logger

from .deps import get_db, get_knowledge_manager, get_workspace_manager
from .schemas import (
    ApiResponse,
    KnowledgeFileItem,
    KnowledgeFilesListData,
    KnowledgeFilesSummary,
    KnowledgeUploadedFile,
    KnowledgeUploadResult,
)

_log = get_logger("pptgenius.api.knowledge")

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _extract_conversation_id(file_path: str) -> int | None:
    """Derive conversation_id from file_path pattern: .../workspace/{id}/..."""
    parts = file_path.replace("\\", "/").split("/")
    try:
        idx = parts.index("workspace")
        return int(parts[idx + 1])
    except (ValueError, IndexError):
        return None


@router.post("/upload", status_code=201)
async def upload_files(
    user_id: int = Form(..., description="User ID"),
    conversation_id: int = Form(..., description="Conversation ID"),
    files: list[UploadFile] = File(...),
    db: Database = Depends(get_db),
    km: KnowledgeService = Depends(get_knowledge_manager),
    wm=Depends(get_workspace_manager),
) -> ApiResponse[KnowledgeUploadResult]:
    result = KnowledgeUploadResult()

    kdir = wm.get_knowledge_dir(conversation_id)
    kdir.mkdir(parents=True, exist_ok=True)

    for f in files:
        try:
            safe_name = f"{int(time.time())}_{Path(f.filename).name}"
            dest = kdir / safe_name

            content = await f.read()
            dest.write_bytes(content)

            file_id = await km.ingest(db, str(dest), user_id)
            if file_id is None:
                result.failed.append({"filename": f.filename, "reason": "parse failed"})
                continue

            result.uploaded.append(KnowledgeUploadedFile(
                id=file_id,
                conversation_id=conversation_id,
                filename=f.filename,
                file_type=dest.suffix.lstrip("."),
                file_size=len(content),
                chunk_count=None,  # filled by ingest; not exposed here
                status="indexed",
            ))
        except Exception as exc:
            _log.exception("upload failed: %s", f.filename)
            result.failed.append({"filename": f.filename, "reason": str(exc)})

    return ApiResponse(data=result)


@router.get("/files")
async def list_files(
    user_id: int = Query(..., description="User ID"),
    conversation_id: int | None = Query(None),
    type: str | None = Query(None, alias="type"),
    source_type: str | None = Query(None),
    status: str | None = Query(None),
    db: Database = Depends(get_db),
) -> ApiResponse[KnowledgeFilesListData]:
    files = await db.list_knowledge_files(
        user_id,
        file_type=type,
        source_type=source_type,
        status=status,
        conversation_id=conversation_id,
    )
    items = []
    total_size = 0
    total_chunks = 0
    for kf in files:
        items.append(KnowledgeFileItem(
            id=kf.id,
            user_id=kf.user_id,
            conversation_id=_extract_conversation_id(kf.file_path),
            filename=kf.filename,
            file_type=kf.file_type,
            file_size=kf.file_size,
            chunk_count=kf.chunk_count,
            source_type=kf.source_type,
            status=kf.status,
            created_at=kf.created_at,
        ))
        total_size += kf.file_size or 0
        total_chunks += kf.chunk_count or 0

    return ApiResponse(data=KnowledgeFilesListData(
        items=items,
        total=len(items),
        summary=KnowledgeFilesSummary(
            total_files=len(items),
            total_size=total_size,
            total_chunks=total_chunks,
        ),
    ))


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: int,
    db: Database = Depends(get_db),
    km: KnowledgeService = Depends(get_knowledge_manager),
) -> ApiResponse[dict]:
    kf = await db.get_knowledge_file(file_id)
    if kf is None:
        raise HTTPException(404, {"code": 40001, "message": "knowledge file not found"})
    ok = await km.remove_file(db, file_id)
    return ApiResponse(data={"deleted": ok, "file_id": file_id})
