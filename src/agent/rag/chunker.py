import re


def chunk_text(
    text: str,
    strategy: str = "paragraph",
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    """Split text into chunks for embedding.

    Strategies:
        paragraph: Split on double newlines, merge small paragraphs.
        fixed: Fixed-size sliding window.
        sentence: Split on sentence boundaries.
    """
    if strategy == "paragraph":
        return _chunk_by_paragraph(text, chunk_size, overlap)
    elif strategy == "fixed":
        return _chunk_fixed(text, chunk_size, overlap)
    elif strategy == "sentence":
        return _chunk_by_sentence(text, chunk_size, overlap)
    else:
        return _chunk_by_paragraph(text, chunk_size, overlap)


def _chunk_by_paragraph(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split by paragraphs, merge small ones to hit chunk_size."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    current = []
    current_len = 0

    for p in paragraphs:
        if current_len + len(p) > chunk_size and current:
            chunks.append("\n".join(current))
            # Keep last items for overlap
            overlap_text = "\n".join(current)
            if len(overlap_text) > overlap:
                current = [overlap_text[-overlap:]]
                current_len = len(current[0])
            else:
                current = []
                current_len = 0
        current.append(p)
        current_len += len(p)

    if current:
        chunks.append("\n".join(current))
    return chunks


def _chunk_fixed(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Fixed-size sliding window chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def _chunk_by_sentence(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split by sentence boundaries, merge to hit chunk_size."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = []
    current_len = 0

    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if current_len + len(s) > chunk_size and current:
            chunks.append(" ".join(current))
            # Overlap: keep last sentences
            overlap_text = " ".join(current)
            words = overlap_text.split()
            keep = max(1, len(words) // 4)
            current = [" ".join(words[-keep:])]
            current_len = len(current[0])
        current.append(s)
        current_len += len(s)

    if current:
        chunks.append(" ".join(current))
    return chunks
