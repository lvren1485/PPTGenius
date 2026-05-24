"""Text chunker — splits parsed documents by paragraph boundaries.

Strategy:
  1. Split on ``\\n\\n`` (paragraph breaks).
  2. Merge consecutive small paragraphs until the token budget is reached.
  3. Keep a configurable overlap (last N chars of previous chunk prepended).
"""

from __future__ import annotations

import tiktoken

_ENC = tiktoken.get_encoding("cl100k_base")


def _token_count(text: str) -> int:
    return len(_ENC.encode(text))


def chunk_text(
    text: str,
    chunk_tokens: int = 500,
    overlap_chars: int = 100,
) -> list[str]:
    """Split *text* into chunks of roughly *chunk_tokens* tokens each.

    Paragraph boundaries (``\\n\\n``) are preferred split points.
    Short paragraphs are merged; long paragraphs are split by sentence.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    buf: list[str] = []
    buf_tokens = 0

    def _flush() -> None:
        nonlocal buf, buf_tokens
        if buf:
            chunks.append("\n\n".join(buf))
            buf = []
            buf_tokens = 0

    for para in paragraphs:
        para_tokens = _token_count(para)

        # If a single paragraph exceeds the budget, split by sentence
        if para_tokens >= chunk_tokens:
            _flush()
            _split_long_paragraph(para, chunks, chunk_tokens)
            continue

        # Would adding this paragraph overflow?
        if buf_tokens + para_tokens > chunk_tokens and buf:
            _flush()

        buf.append(para)
        buf_tokens += para_tokens

    _flush()

    # Apply overlap
    if overlap_chars > 0 and len(chunks) > 1:
        overlapped: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            tail = prev[-overlap_chars:] if len(prev) > overlap_chars else prev
            overlapped.append(tail + "\n\n" + chunks[i])
        return overlapped

    return chunks


def _split_long_paragraph(text: str, out: list[str], chunk_tokens: int) -> None:
    """Split an overly-long paragraph by sentence boundaries."""
    import re
    sentences = re.split(r"(?<=[。.！!？?\n])\s*", text)
    buf: list[str] = []
    buf_tokens = 0

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        st = _token_count(sent)
        if buf_tokens + st > chunk_tokens and buf:
            out.append(" ".join(buf))
            buf = []
            buf_tokens = 0
        buf.append(sent)
        buf_tokens += st

    if buf:
        out.append(" ".join(buf))
