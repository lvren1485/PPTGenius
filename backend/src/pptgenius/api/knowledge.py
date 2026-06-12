"""Knowledge file management endpoints.

BM25 retrieval is internal to the agent — not exposed via HTTP.

Image files are saved to the workspace input/ dir and an image-message is
created; they do not enter the BM25 index. All other files are parsed,
chunked, indexed, and a file-message with a text preview is created.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.rag import KnowledgeService
from pptgenius.infrastructure.rag.parser import parse_file
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

_IMAGE_SUFFIXES = frozenset({"png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico", "tiff", "tif"})


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
            suffix = Path(f.filename).suffix.lower().lstrip(".")
            safe_name = f"{int(time.time())}_{Path(f.filename).name}"
            content = await f.read()

            # ── Image: save to input/ dir, create image-message, skip BM25 ──
            if suffix in _IMAGE_SUFFIXES:
                idir = wm.get_input_dir(conversation_id)
                idir.mkdir(parents=True, exist_ok=True)
                dest = idir / safe_name
                dest.write_bytes(content)

                rel_path = os.path.relpath(str(dest), str(wm.get_path(conversation_id)))

                try:
                    await db.create_message(
                        conversation_id=conversation_id,
                        role="image",
                        content=(
                            f"[Image uploaded: {f.filename}]\n"
                            f"Path: {rel_path}\n"
                            f"Type: {suffix} | {len(content)} bytes"
                        ),
                        content_type="image",
                    )
                except Exception:
                    _log.exception("Failed to create image message for %s", f.filename)

                result.uploaded.append(KnowledgeUploadedFile(
                    id=None,  # images don't get a knowledge_file row
                    conversation_id=conversation_id,
                    filename=f.filename,
                    file_type=suffix,
                    file_size=len(content),
                    chunk_count=None,
                    status="saved",
                ))
                continue

            # ── Document: parse → ingest (BM25) → file-message with preview ──
            dest = kdir / safe_name
            dest.write_bytes(content)

            file_id = await km.ingest(db, str(dest), user_id, conversation_id)
            if file_id is None:
                result.failed.append({"filename": f.filename, "reason": "parse failed"})
                continue

            try:
                doc = parse_file(str(dest))
                preview = doc.text[:200].strip()
                if preview:
                    await db.create_message(
                        conversation_id=conversation_id,
                        role="file",
                        content=(
                            f"[File uploaded: {f.filename}]\n"
                            f"Type: {doc.file_type} | {doc.char_count} chars\n"
                            f"---\n"
                            f"{preview}"
                        ),
                        content_type="file",
                    )
            except Exception:
                _log.exception("Failed to create file message for %s", f.filename)

            result.uploaded.append(KnowledgeUploadedFile(
                id=file_id,
                conversation_id=conversation_id,
                filename=f.filename,
                file_type=dest.suffix.lstrip("."),
                file_size=len(content),
                chunk_count=None,
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
