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
        output_path = str(config.OUTPUT_DIR / f"presentation.pptx")

    return {
        "status": "pending",
        "output_path": output_path,
        "slide_count": len(outline.slides),
        "template": template,
        "note": "PPT generation requires the full pipeline (ppt/generator.py).",
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

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))

    if chart_type == "bar":
        ax.bar(data.get("labels", []), data.get("values", []))
    elif chart_type == "line":
        ax.plot(data.get("labels", []), data.get("values", []), marker="o")
    elif chart_type == "pie":
        ax.pie(data.get("values", []), labels=data.get("labels", []), autopct="%1.1f%%")
    elif chart_type == "scatter":
        ax.scatter(data.get("x", []), data.get("y", []))
    elif chart_type == "histogram":
        ax.hist(data.get("values", []), bins=data.get("bins", 10))
    else:
        return {"error": f"Unknown chart type: {chart_type}"}

    if title:
        ax.set_title(title)

    image_path = config.OUTPUT_DIR / f"chart_{title.replace(' ', '_')[:20]}.png"
    plt.tight_layout()
    plt.savefig(str(image_path), dpi=150)
    plt.close()

    return {"image_path": str(image_path)}


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
