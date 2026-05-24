"""Document parser — dispatches by file extension.

Usage::

    from pptgenius.infrastructure.rag.parser import parse_file

    doc = parse_file("path/to/file.docx")
    print(doc.text[:200])
"""

from __future__ import annotations

from pathlib import Path

from .base import ParsedDocument

_PARSERS: dict[str, object] = {}


def _ensure_registry() -> None:
    if _PARSERS:
        return
    from .docx_parser import parse_docx
    from .pdf_parser import parse_pdf
    from .pptx_parser import parse_pptx
    from .spreadsheet_parser import parse_spreadsheet
    from .text_parser import parse_text

    _PARSERS.update({
        "docx": parse_docx,
        "doc":  parse_docx,
        "pdf":  parse_pdf,
        "pptx": parse_pptx,
        "csv":  parse_spreadsheet,
        "xlsx": parse_spreadsheet,
        "xls":  parse_spreadsheet,
        "md":   parse_text,
        "txt":  parse_text,
    })


def parse_file(file_path: str | Path) -> ParsedDocument:
    """Parse *file_path* into a :class:`ParsedDocument`."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"file not found: {file_path}")

    suffix = path.suffix.lower().lstrip(".")
    _ensure_registry()

    parser = _PARSERS.get(suffix)
    if parser is None:
        raise ValueError(f"unsupported file type: .{suffix}")

    return parser(str(path))  # type: ignore[operator]
