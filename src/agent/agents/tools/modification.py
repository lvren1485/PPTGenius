"""Tools for modifying existing slides (content and layout)."""

from pathlib import Path

from .registry import register
from ...config import config


@register
def modify_slide_content(slide_index: int, changes: str, ppt_path: str | None = None) -> dict:
    """Modify the text content of an existing slide without affecting layout.

    Args:
        slide_index: 0-based index of the slide to modify.
        changes: Natural language description of the content changes.
        ppt_path: Path to the PPT file (default: most recent in output/).

    Returns:
        Dict with status and description of changes made.
    """
    if ppt_path is None:
        ppt_path = str(_find_latest_ppt())
    return {
        "status": "pending",
        "message": f"Content changes requested for slide {slide_index}: {changes}",
        "ppt_path": ppt_path,
        "note": "Content modification requires the full agent pipeline to apply.",
    }


@register
def modify_slide_layout(slide_index: int, layout: str, ppt_path: str | None = None) -> dict:
    """Change the layout of an existing slide without altering content.

    Args:
        slide_index: 0-based index of the slide to modify.
        layout: Target layout type (title, section, content, two_column, ending).
        ppt_path: Path to the PPT file (default: most recent in output/).

    Returns:
        Dict with status and description of changes made.
    """
    if ppt_path is None:
        ppt_path = str(_find_latest_ppt())
    return {
        "status": "pending",
        "message": f"Layout change requested for slide {slide_index}: {layout}",
        "ppt_path": ppt_path,
        "note": "Layout modification requires the full agent pipeline to apply.",
    }


def _find_latest_ppt() -> Path:
    """Find the most recent .pptx file in the output directory."""
    output_dir = config.OUTPUT_DIR
    ppt_files = list(output_dir.glob("*.pptx"))
    if not ppt_files:
        return output_dir / "presentation.pptx"
    return max(ppt_files, key=lambda p: p.stat().st_mtime)
