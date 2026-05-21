"""Tests for RAG chunker and parser utilities."""

from agent.rag.chunker import chunk_text
from agent.rag.parsers.txt_parser import parse_text
import tempfile


def test_chunk_paragraph():
    text = "A" * 300 + "\n\n" + "B" * 300
    chunks = chunk_text(text, strategy="paragraph", chunk_size=200, overlap=20)
    assert len(chunks) >= 2


def test_chunk_fixed():
    text = "A" * 1000
    chunks = chunk_text(text, strategy="fixed", chunk_size=200, overlap=50)
    assert len(chunks) >= 5


def test_chunk_empty():
    chunks = chunk_text("", strategy="paragraph")
    assert chunks == []


def test_parse_txt():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello World")
        path = f.name
    content = parse_text(path)
    assert content == "Hello World"
    import os
    os.unlink(path)
