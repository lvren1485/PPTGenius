"""Tools for generating PPT, charts, and tables."""

import json
from pathlib import Path

from .registry import register
from ...models.outline import PresentationOutline, SlideOutline
from ...config import config


@register
def generate_ppt(
    outline_json: str,
    template: str = "professional-blue",
    output_path: str | None = None,
) -> dict:
    """Generate a PPT file from a structured outline.

    Args:
        outline_json: JSON string matching PresentationOutline schema
            (containing topic, slides list with title/subtitle/bullets/layout_type).
        template: Template name (default: professional-blue).
        output_path: Custom output path (default: auto-generated in output/).

    Returns:
        Dict with output_path, slide_count, and template used.
    """
    # Parse the outline
    try:
        data = json.loads(outline_json)
        outline = PresentationOutline(**data)
    except Exception as e:
        return {"error": f"Invalid outline JSON: {e}"}

    if output_path is None:
        output_path = str(config.OUTPUT_DIR / f"{outline.topic[:20].replace(' ', '_')}.pptx")

    from ...ppt.generator import generate_presentation
    real_path = generate_presentation(outline, template, output_path)

    return {
        "status": "success",
        "output_path": real_path,
        "slide_count": len(outline.slides),
        "template": template,
    }


@register
def generate_chart(
    chart_type: str,
    data_json: str,
    title: str = "",
) -> dict:
    """Generate a chart image from data using matplotlib.

    Args:
        chart_type: Type of chart (bar, line, pie, scatter, histogram).
        data_json: JSON string containing chart data.
            For bar/line: {"labels": [...], "values": [...]}
            For pie: {"labels": [...], "values": [...]}
            For scatter: {"x": [...], "y": [...]}
        title: Chart title text.

    Returns:
        Dict with image_path where the chart was saved.
    """
    try:
        data = json.loads(data_json)
    except Exception as e:
        return {"error": f"Invalid data JSON: {e}"}

    from ...ppt.charts import generate_chart_image
    image_path = generate_chart_image(chart_type, data, title)
    return {"image_path": image_path}


@register
def generate_table(headers: list, rows: list) -> dict:
    """Generate a formatted table data structure for a slide.

    Args:
        headers: List of column header strings.
        rows: List of lists, each inner list is a row of cell values.

    Returns:
        Dict with table data in a structured format.
    """
    return {
        "headers": headers,
        "rows": rows,
        "row_count": len(rows),
        "col_count": len(headers),
    }
