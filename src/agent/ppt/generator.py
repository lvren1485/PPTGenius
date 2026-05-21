"""Main PPT generator: converts a structured outline into a .pptx file."""

from pathlib import Path
from pptx import Presentation
from pptx.util import Inches

from ..models.outline import PresentationOutline
from .templates import get_template
from .slides import (
    build_title_slide,
    build_section_slide,
    build_content_slide,
    build_two_column_slide,
    build_ending_slide,
)
from ..config import config


def generate_presentation(
    outline: PresentationOutline,
    template_name: str = "professional-blue",
    output_path: str | None = None,
) -> str:
    """Generate a .pptx file from a structured outline.

    Args:
        outline: PresentationOutline with slides list.
        template_name: Name of the template to use.
        output_path: Output file path (auto-generated if None).

    Returns:
        Path to the generated .pptx file.
    """
    template = get_template(template_name)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    for slide_data in outline.slides:
        layout = slide_data.layout_type

        if layout == "title":
            build_title_slide(prs, template, slide_data.title, slide_data.subtitle or "")

        elif layout == "section":
            build_section_slide(prs, template, slide_data.title)

        elif layout == "two_column":
            mid = len(slide_data.bullets) // 2
            build_two_column_slide(
                prs, template, slide_data.title,
                left_items=slide_data.bullets[:mid],
                right_items=slide_data.bullets[mid:],
            )

        elif layout == "ending":
            build_ending_slide(prs, template, slide_data.title, slide_data.subtitle or "")

        else:
            # Default: content slide
            build_content_slide(prs, template, slide_data.title, slide_data.bullets)

    # Save
    if output_path is None:
        output_path = str(config.OUTPUT_DIR / "presentation.pptx")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return str(path)
