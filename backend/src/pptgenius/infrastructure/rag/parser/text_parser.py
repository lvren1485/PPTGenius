"""Markdown / plain-text parser."""

from __future__ import annotations

from pathlib import Path

from .base import ParsedDocument, _normalise_text


def parse_text(file_path: str | Path) -> ParsedDocument:
    """Read a .md or .txt file and return its text content."""
    path = Path(file_path)
    raw = path.read_text(encoding="utf-8")
    text = _normalise_text(raw)
    return ParsedDocument(
        file_path=str(path),
        file_type=path.suffix.lower().lstrip("."),
        text=text,
        metadata={"filename": path.name},
    )
