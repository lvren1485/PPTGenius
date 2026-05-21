"""Slide builder functions for each layout type."""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

from .styles import (
    MARGIN_LEFT, MARGIN_TOP, CONTENT_WIDTH, TITLE_TOP, TITLE_HEIGHT,
    BODY_TOP, BODY_HEIGHT,
)
from .templates import Template


def _add_text_box(slide, left, top, width, height, text, font_name, font_size,
                  color, bold=False, alignment=PP_ALIGN.LEFT):
    """Add a text box to a slide with specified formatting."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.name = font_name
    p.font.size = Pt(font_size)
    p.font.color.rgb = RGBColor(*bytes.fromhex(color.lstrip("#")))
    p.font.bold = bold
    p.alignment = alignment
    return tf


def _add_bullets(tf, bullets, font_name, font_size, color):
    """Add bullet points to an existing text frame."""
    for bullet in bullets:
        p = tf.add_paragraph()
        p.text = bullet
        p.font.name = font_name
        p.font.size = Pt(font_size)
        p.font.color.rgb = RGBColor(*bytes.fromhex(color.lstrip("#")))
        p.level = 0
        p.space_after = Pt(6)
    return tf


def build_title_slide(prs: Presentation, template: Template, title: str, subtitle: str = ""):
    """Build a title slide with centered title and optional subtitle."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(*bytes.fromhex(template.colors.bg.lstrip("#")))

    _add_text_box(
        slide, Inches(1), Inches(2), Inches(11), Inches(1.5),
        title, template.fonts.title, 44, template.colors.accent,
        bold=True, alignment=PP_ALIGN.CENTER,
    )
    if subtitle:
        _add_text_box(
            slide, Inches(1), Inches(3.8), Inches(11), Inches(1),
            subtitle, template.fonts.body, 24, template.colors.text,
            alignment=PP_ALIGN.CENTER,
        )
    return slide


def build_content_slide(prs: Presentation, template: Template, title: str, bullets: list[str]):
    """Build a standard content slide with title and bullet points."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(*bytes.fromhex(template.colors.bg.lstrip("#")))

    # Title
    tf = _add_text_box(
        slide, MARGIN_LEFT, TITLE_TOP, CONTENT_WIDTH, TITLE_HEIGHT,
        title, template.fonts.title, 32, template.colors.accent, bold=True,
    )

    # Accent line under title
    _add_text_box(
        slide, MARGIN_LEFT, Inches(1.2), Inches(2), Inches(0.05),
        "—" * 20, template.fonts.body, 8, template.colors.highlight,
    )

    # Bullet content
    if bullets:
        body_tf = _add_text_box(
            slide, MARGIN_LEFT, BODY_TOP, CONTENT_WIDTH, BODY_HEIGHT,
            "", template.fonts.body, 18, template.colors.text,
        )
        body_tf.paragraphs[0].text = bullets[0] if bullets else ""
        if len(bullets) > 1:
            _add_bullets(body_tf, bullets[1:], template.fonts.body, 18, template.colors.text)
    return slide


def build_section_slide(prs: Presentation, template: Template, title: str):
    """Build a section divider slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(*bytes.fromhex(template.colors.accent.lstrip("#")))

    _add_text_box(
        slide, Inches(1), Inches(2.5), Inches(11), Inches(2),
        title, template.fonts.title, 40, template.colors.bg,
        bold=True, alignment=PP_ALIGN.CENTER,
    )
    return slide


def build_two_column_slide(prs: Presentation, template: Template, title: str,
                           left_items: list[str], right_items: list[str]):
    """Build a two-column comparison slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(*bytes.fromhex(template.colors.bg.lstrip("#")))

    # Title
    _add_text_box(
        slide, MARGIN_LEFT, TITLE_TOP, CONTENT_WIDTH, TITLE_HEIGHT,
        title, template.fonts.title, 32, template.colors.accent, bold=True,
    )

    # Left column
    col_width = Inches(5.2)
    left_tf = _add_text_box(
        slide, MARGIN_LEFT, BODY_TOP, col_width, BODY_HEIGHT,
        "", template.fonts.body, 16, template.colors.text,
    )
    if left_items:
        left_tf.paragraphs[0].text = left_items[0]
        _add_bullets(left_tf, left_items[1:], template.fonts.body, 16, template.colors.text)

    # Right column
    right_tf = _add_text_box(
        slide, Inches(6.8), BODY_TOP, col_width, BODY_HEIGHT,
        "", template.fonts.body, 16, template.colors.text,
    )
    if right_items:
        right_tf.paragraphs[0].text = right_items[0]
        _add_bullets(right_tf, right_items[1:], template.fonts.body, 16, template.colors.text)
    return slide


def build_ending_slide(prs: Presentation, template: Template, title: str = "Thank You",
                       subtitle: str = ""):
    """Build an ending/conclusion slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(*bytes.fromhex(template.colors.highlight.lstrip("#")))

    _add_text_box(
        slide, Inches(1), Inches(2.5), Inches(11), Inches(1.5),
        title, template.fonts.title, 44, template.colors.bg,
        bold=True, alignment=PP_ALIGN.CENTER,
    )
    if subtitle:
        _add_text_box(
            slide, Inches(1), Inches(4.2), Inches(11), Inches(1),
            subtitle, template.fonts.body, 22, template.colors.bg,
            alignment=PP_ALIGN.CENTER,
        )
    return slide
