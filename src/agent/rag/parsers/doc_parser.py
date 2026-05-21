from pathlib import Path


def parse_docx(file_path: str | Path) -> str:
    """Extract text from a .docx file using python-docx."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"DOCX not found: {path}")

    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx is required for DOCX parsing")

    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)
