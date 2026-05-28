"""Layout resolver — container bounds calculation and relative position resolution.

Given a layout definition and the outline slide, computes:
  - Which layout to use
  - Container bounds for sub-agent context
  - Variable interpolation ({{primary}} → actual color)

Reuses infrastructure.ppt_engine.parser.base.resolve_position() for the actual
coordinate math.
"""

from __future__ import annotations

from pptgenius.infrastructure.config import get_settings

# Slide dimensions (16:9)
SLIDE_W = 13.333
SLIDE_H = 7.5

# ── layout type → layout name mapping ──


LAYOUT_MAP: dict[str, str] = {
    "title": "title_slide",
    "section": "section",
    "content": "content_bullet",      # default, overridden by recommended_ppt_format
    "summary": "content_bullet",
    "thanks": "ending",
}

# recommended_ppt_format → layout override (for content type)
FORMAT_LAYOUT_MAP: dict[str, str] = {
    "two_column": "content_two_column",
    "comparison": "content_two_column",
    "three_column": "content_three_column",
    "four_grid": "content_grid_2x2",
    # bullet_list, text_with_image, chart, table, diagram, flowchart → content_bullet
}


def select_layout(outline_slide: dict) -> str:
    """Determine which layout to use for a given outline slide."""
    layout_type = outline_slide.get("layout_type", "content")

    if layout_type in ("title", "section", "summary", "thanks"):
        return LAYOUT_MAP[layout_type]

    # content type — check recommended_ppt_format for overrides
    content_json = outline_slide.get("content_json", {})
    if isinstance(content_json, dict):
        fmt = content_json.get("recommended_ppt_format", "")
        if fmt in FORMAT_LAYOUT_MAP:
            return FORMAT_LAYOUT_MAP[fmt]

    return "content_bullet"


# ── container bounds ──


# Pre-computed container bounds for sub-agent context injection
CONTAINER_BOUNDS: dict[str, dict[str, float]] = {
    "slide":     {"left": 0,     "top": 0,    "width": 13.333, "height": 7.5},
    "left_col":  {"left": 0.5,   "top": 1.6,  "width": 5.8,    "height": 5.1},
    "right_col": {"left": 6.8,   "top": 1.6,  "width": 5.8,    "height": 5.1},
    "col_0":     {"left": 0.3,   "top": 1.6,  "width": 3.9,    "height": 5.1},
    "col_1":     {"left": 4.5,   "top": 1.6,  "width": 3.9,    "height": 5.1},
    "col_2":     {"left": 8.7,   "top": 1.6,  "width": 3.9,    "height": 5.1},
    "grid_00":   {"left": 0.5,   "top": 1.6,  "width": 5.8,    "height": 2.5},
    "grid_01":   {"left": 6.8,   "top": 1.6,  "width": 5.8,    "height": 2.5},
    "grid_10":   {"left": 0.5,   "top": 4.3,  "width": 5.8,    "height": 2.5},
    "grid_11":   {"left": 6.8,   "top": 4.3,  "width": 5.8,    "height": 2.5},
}


def get_container_bounds(layout_definition: dict) -> dict[str, dict[str, float]]:
    """Extract container bounds from a layout definition.

    Returns a dict of {container_id: {left, top, width, height}} that can be
    injected into sub-agent prompts for relative positioning.
    """
    bounds = {"slide": CONTAINER_BOUNDS["slide"]}
    for c in layout_definition.get("containers", []):
        cid = c["id"]
        if cid in CONTAINER_BOUNDS:
            bounds[cid] = dict(CONTAINER_BOUNDS[cid])
        else:
            bounds[cid] = dict(c["position"])
    return bounds


def format_container_prompt(bounds: dict[str, dict[str, float]], parent_id: str) -> str:
    """Format container bounds as a readable prompt section for a sub-agent."""
    if parent_id == "slide":
        return "容器: slide (整个幻灯片 13.333×7.5 英寸)，使用绝对坐标。"

    pb = bounds.get(parent_id, CONTAINER_BOUNDS["slide"])
    return (
        f"容器: parent='{parent_id}'\n"
        f"容器 bounds: left={pb['left']}, top={pb['top']}, "
        f"width={pb['width']}, height={pb['height']}\n"
        f"使用相对坐标（相对容器左上角），position.parent 设为 '{parent_id}'。"
    )


# ── variable interpolation ──


def interpolate_layout(layout_def: dict, color_scheme: dict) -> dict:
    """Replace {{primary}}, {{bg}}, etc. with actual color values.

    Returns a deep-copied layout definition with all variables resolved.
    """
    import copy, json, re

    colors = color_scheme.get("colors", {})
    _VAR_RE = re.compile(r"\{\{(\w+)\}\}")

    def _replace(obj):
        if isinstance(obj, str):
            return _VAR_RE.sub(lambda m: colors.get(m.group(1), m.group(0)), obj)
        elif isinstance(obj, dict):
            return {k: _replace(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_replace(v) for v in obj]
        return obj

    return _replace(copy.deepcopy(layout_def))
