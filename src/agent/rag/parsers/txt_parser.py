from pathlib import Path


def parse_text(file_path: str | Path) -> str:
    """Read plain text from a file (txt, md, rst, json, etc.)."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")
