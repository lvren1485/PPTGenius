from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from ppt_generator.core import PPTGenerator
from ppt_generator.server.extract import ExtractError, extract_document_text, slug_filename


def _try_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[3]
    load_dotenv(root / ".env")


_try_load_dotenv()


def _parse_num_slides(raw: str) -> int:
    try:
        n = int(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="num_slides 必须为整数") from e
    if n < 1 or n > 40:
        raise HTTPException(status_code=400, detail="num_slides 需在 1–40 之间")
    return n


def create_app() -> FastAPI:
    app = FastAPI(title="PPT-Genius API", version="0.1.0")

    origins = os.environ.get("PPTGENIUS_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
    origins = [o.strip() for o in origins if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/generate")
    async def generate(
        background_tasks: BackgroundTasks,
        topic: str = Form(...),
        num_slides: str = Form("10"),
        files: Optional[List[UploadFile]] = File(None),
    ) -> FileResponse:
        topic_clean = topic.strip()
        if not topic_clean:
            raise HTTPException(status_code=400, detail="主题不能为空")

        n = _parse_num_slides(num_slides.strip())

        extra_docs: list[tuple[str, str]] = []
        upload_list = files or []
        for uf in upload_list:
            if not uf.filename:
                continue
            raw = await uf.read()
            if not raw:
                continue
            try:
                text = extract_document_text(uf.filename, raw)
            except ExtractError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if not text:
                raise HTTPException(status_code=400, detail=f"文件「{uf.filename}」未解析出可用文本")
            safe_name = os.path.basename(uf.filename)
            extra_docs.append((safe_name, text))

        generator = PPTGenerator(extra_documents=extra_docs if extra_docs else None)
        outline = generator.generate_outline(topic=topic_clean, num_slides=n)
        enhanced = generator.enhance_with_rag(outline)

        fd, tmp_path = tempfile.mkstemp(suffix=".pptx")
        os.close(fd)
        try:
            enhanced.export(tmp_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        download_name = f"{slug_filename(topic_clean)}.pptx"

        def _cleanup() -> None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        background_tasks.add_task(_cleanup)
        return FileResponse(
            tmp_path,
            filename=download_name,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

    return app


app = create_app()
