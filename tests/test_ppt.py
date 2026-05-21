"""Tests for PPT generation."""

from agent.models.outline import PresentationOutline, SlideOutline
from agent.ppt.generator import generate_presentation
from agent.ppt.templates import get_template, TEMPLATES


def test_generate_simple_ppt(tmp_path):
    outline = PresentationOutline(
        topic="Test",
        slides=[
            SlideOutline(title="Title", subtitle="Sub", layout_type="title"),
            SlideOutline(title="Content", bullets=["A", "B"], layout_type="content"),
            SlideOutline(title="End", layout_type="ending"),
        ],
    )
    output = tmp_path / "test.pptx"
    path = generate_presentation(outline, output_path=str(output))
    assert output.exists()
    assert path == str(output)


def test_all_templates(tmp_path):
    outline = PresentationOutline(
        topic="Test",
        slides=[SlideOutline(title="Slide 1", bullets=["x"], layout_type="content")],
    )
    for name in TEMPLATES:
        output = tmp_path / f"test_{name}.pptx"
        path = generate_presentation(outline, template_name=name, output_path=str(output))
        assert path
        assert output.exists()
        output.unlink()


def test_get_template_default():
    t = get_template()
    assert t.name == "Professional Blue"


def test_get_template_by_name():
    t = get_template("modern-teal")
    assert t.name == "Modern Teal"
    assert t.colors.accent == "#00B894"


def test_invalid_template_falls_back():
    t = get_template("nonexistent")
    assert t.name == "Professional Blue"
