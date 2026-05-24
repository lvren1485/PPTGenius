""".pdf parser via PyMuPDF (fitz)."""

from __future__ import annotations

from pathlib import Path

import fitz

from .base import ParsedDocument, _normalise_text


def parse_pdf(file_path: str | Path) -> ParsedDocument:
    """Extract text from a .pdf file via PyMuPDF."""
    path = Path(file_path)
    doc = fitz.open(str(path))

    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())

    raw = "\n".join(pages)
    text = _normalise_text(raw)
    page_count = len(doc)
    doc.close()
    return ParsedDocument(
        file_path=str(path),
        file_type="pdf",
        text=text,
        metadata={
            "filename": path.name,
            "pages": page_count,
        },
    )
