"""PPT Generator — validates then builds .pptx from instruction JSON."""

from __future__ import annotations

import logging
import os
from typing import Any

from pptx import Presentation
from pptx.util import Inches

from .parser.base import PPTInstruction
from .validator import ValidationResult, validate_instruction
from .parser.chart_parser import render_chart
from .parser.table_parser import render_table
from .parser.text_parser import render_textbox
from .parser.image_parser import render_picture
from .parser.shape_parser import render_shape

logger = logging.getLogger("ppt_engine.generator")


async def generate_ppt(
    data: dict[str, Any],
    output_path: str,
    workspace_path: str | None = None,
) -> dict[str, Any]:
    """Validate instruction JSON, then generate .pptx.

    Returns:
        {"ok": True, "path": "...", "slide_count": N} or {"ok": False, "errors": [...]}
    """
    logger.info("Starting PPT generation → %s", output_path)

    # ── Validate ──
    result: ValidationResult = validate_instruction(data)
    if not result.is_valid:
        logger.warning("Validation failed, aborting generation")
        return {"ok": False, "errors": result.errors}

    instruction: PPTInstruction = result.parsed
    meta = instruction.meta
    logger.info("Validation OK, building %d slide(s)", len(instruction.slides))

    # ── Build ──
    prs = Presentation()
    prs.slide_width = Inches(meta.slide_width)
    prs.slide_height = Inches(meta.slide_height)
    ws = workspace_path or "."

    for si, slide_spec in enumerate(instruction.slides):
        layout_idx = _find_layout_index(prs, slide_spec.layout)
        slide = prs.slides.add_slide(prs.slide_layouts[layout_idx])
        logger.debug("Slide %d/%d: layout=%s (%d element(s))",
                     si + 1, len(instruction.slides), slide_spec.layout, len(slide_spec.elements))

        for ei, element in enumerate(slide_spec.elements):
            try:
                if element.type == "textbox":
                    render_textbox(slide, element)
                elif element.type == "chart":
                    render_chart(slide, element)
                elif element.type == "table":
                    render_table(slide, element)
                elif element.type == "picture":
                    render_picture(slide, element, ws)
                elif element.type == "shape":
                    render_shape(slide, element)
            except Exception as exc:
                logger.exception("Render failed: slides[%d].elements[%d] (%s)", si, ei, element.type)
                return {"ok": False, "errors": [{
                    "path": f"slides[{si}].elements[{ei}]",
                    "error": f"Render failed: {exc}",
                }]}

    # ── Save ──
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    prs.save(output_path)
    file_size = os.path.getsize(output_path)
    logger.info("PPT saved: %s (%d bytes, %d slides)", output_path, file_size, len(instruction.slides))
    return {"ok": True, "path": output_path, "slide_count": len(instruction.slides), "file_size": file_size}


def _find_layout_index(prs, layout_name: str) -> int:
    """Find layout index by name. Falls back to blank (6)."""
    for i, lo in enumerate(prs.slide_layouts):
        if lo.name == layout_name:
            return i
    for i, lo in enumerate(prs.slide_layouts):
        if layout_name in lo.name or lo.name in layout_name:
            return i
    return 6
