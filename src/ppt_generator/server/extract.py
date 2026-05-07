from __future__ import annotations

import io
import re
from pathlib import Path


class ExtractError(ValueError):
    pass


def extract_document_text(filename: str, raw: bytes) -> str:
    """从上传文件中抽取纯文本，供 RAG 切块索引。"""
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".markdown", ".csv", ".json"}:
        return raw.decode("utf-8", errors="replace").strip()

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise ExtractError("服务器未安装 PDF 解析依赖（pypdf）") from e
        reader = PdfReader(io.BytesIO(raw))
        parts: list[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                parts.append(t)
        return "\n".join(parts).strip()

    if suffix == ".docx":
        try:
            import docx
        except ImportError as e:
            raise ExtractError("服务器未安装 Word 解析依赖（python-docx）") from e
        document = docx.Document(io.BytesIO(raw))
        return "\n".join(p.text for p in document.paragraphs if p.text.strip()).strip()

    raise ExtractError(f"暂不支持的文件类型：{suffix or '无扩展名'}")


def slug_filename(topic: str, default: str = "presentation") -> str:
    base = topic.strip() or default
    base = re.sub(r"[^\w\u4e00-\u9fff]+", "_", base, flags=re.UNICODE).strip("_")
    return base[:80] if base else default
