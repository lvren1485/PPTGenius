"""Test text chunker."""
from pptgenius.infrastructure.rag.chunker import chunk_text


class TestChunker:
    def test_empty(self):
        assert chunk_text("") == []

    def test_single_paragraph(self):
        c = chunk_text("Hello world.", chunk_tokens=500)
        assert len(c) == 1
        assert "Hello" in c[0]

    def test_multi_paragraph(self):
        text = "\n\n".join([f"Paragraph {i} with some content." for i in range(10)])
        chunks = chunk_text(text, chunk_tokens=30)
        assert len(chunks) >= 2

    def test_long_paragraph_split(self):
        text = "Very long sentence. " * 200
        chunks = chunk_text(text, chunk_tokens=100)
        assert len(chunks) > 1

    def test_overlap(self):
        text = "\n\n".join([f"Paragraph number {i}." for i in range(20)])
        chunks = chunk_text(text, chunk_tokens=30, overlap_chars=20)
        assert len(chunks) >= 2

    def test_preserves_content(self):
        text = "Hello world.\n\nThis is a test.\n\nThird paragraph."
        chunks = chunk_text(text, chunk_tokens=500)
        combined = " ".join(chunks)
        for word in ["Hello", "test", "Third"]:
            assert word in combined
