from pathlib import Path

from .pdf_parser import parse_pdf
from .doc_parser import parse_docx
from .ppt_parser import parse_pptx
from .txt_parser import parse_text
from .data_parser import parse_data_file


def parse_file(file_path: str | Path) -> tuple[str | None, str]:
    """Parse a file and return (text_content, file_type).

    Returns:
        (text_content, file_type) where file_type is 'text' or 'data'.
        text_content is None for data files (they go to SQLite instead).
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in (".pdf",):
        return parse_pdf(path), "text"
    elif ext in (".doc", ".docx"):
        return parse_docx(path), "text"
    elif ext in (".ppt", ".pptx"):
        return parse_pptx(path), "text"
    elif ext in (".txt", ".md", ".rst", ".json", ".yaml", ".yml", ".xml", ".html"):
        return parse_text(path), "text"
    elif ext in (".csv", ".xls", ".xlsx"):
        return parse_data_file(path), "data"
    else:
        return None, "unknown"
