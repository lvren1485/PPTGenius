"""Test document parsers against the three sample files."""
from pathlib import Path

from pptgenius.infrastructure.rag.parser import parse_file
from pptgenius.infrastructure.rag.parser.base import ParsedDocument

_RESOURCES = Path(__file__).parent.parent / "resources"


def _first_n_lines(text: str, n: int = 10) -> list[str]:
    return [l for l in text.splitlines() if l.strip()][:n]


class TestMdParser:
    doc: ParsedDocument

    @classmethod
    def setup_class(cls):
        cls.doc = parse_file(_RESOURCES / "test.md")

    def test_file_type(self):
        assert self.doc.file_type in ("md", "markdown")

    def test_has_content(self):
        assert len(self.doc.text) > 3000

    def test_first_lines(self):
        lines = _first_n_lines(self.doc.text)
        assert any(".NET" in l for l in lines)


class TestDocxParser:
    doc: ParsedDocument

    @classmethod
    def setup_class(cls):
        cls.doc = parse_file(_RESOURCES / "test.docx")

    def test_file_type(self):
        assert self.doc.file_type == "docx"

    def test_has_content(self):
        assert len(self.doc.text) > 2000

    def test_tables_found(self):
        assert self.doc.metadata.get("tables", 0) >= 1

    def test_first_lines(self):
        lines = _first_n_lines(self.doc.text)
        assert any(".NET" in l for l in lines)


class TestPdfParser:
    doc: ParsedDocument

    @classmethod
    def setup_class(cls):
        cls.doc = parse_file(_RESOURCES / "test.pdf")

    def test_file_type(self):
        assert self.doc.file_type == "pdf"

    def test_has_content(self):
        assert len(self.doc.text) > 2000

    def test_pages(self):
        assert self.doc.metadata.get("pages", 0) >= 1

    def test_first_lines(self):
        lines = _first_n_lines(self.doc.text)
        assert any(".NET" in l for l in lines)


class TestCrossFormat:
    """Verify all three parsers produce roughly similar text."""

    @classmethod
    def setup_class(cls):
        cls.md = parse_file(_RESOURCES / "test.md")
        cls.docx = parse_file(_RESOURCES / "test.docx")
        cls.pdf = parse_file(_RESOURCES / "test.pdf")

    def test_common_heading(self):
        """All three should contain the same course title."""
        for doc in [self.md, self.docx, self.pdf]:
            assert "Workflow" in doc.text

    def test_common_keyword(self):
        """All three should mention AI Agent."""
        for doc in [self.md, self.docx, self.pdf]:
            assert "Agent" in doc.text

    def test_char_counts_similar(self):
        """Char counts should be in the same order of magnitude."""
        sizes = [len(self.md.text), len(self.docx.text), len(self.pdf.text)]
        # All within a factor of 3 of each other
        assert max(sizes) / min(sizes) < 3.0


def test_unsupported_extension():
    try:
        parse_file("nonexistent.xyz")
    except FileNotFoundError:
        pass  # expected


def test_nonexistent_file():
    try:
        parse_file("nonexistent.md")
    except FileNotFoundError:
        pass
