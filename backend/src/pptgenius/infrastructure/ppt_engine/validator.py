"""Central validator for PPT instruction JSON.

``validate_instruction(dict) → ValidationResult``
  - Pydantic struct validation (all fields, types, enums).
  - Cross-element consistency checks (chart series length, table bounds, etc.).
  - Tests ALL objects at once, collects every error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .parser.base import (
    PPTInstruction,
    ChartElement,
    TableElement,
    TextboxElement,
    ImageElement,
    ShapeElement,
)

logger = logging.getLogger("ppt_engine.validator")


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[dict] = field(default_factory=list)
    # {"path": "slides[0].elements[2].chart_type", "error": "..."}
    parsed: PPTInstruction | None = None


def validate_instruction(data: dict[str, Any]) -> ValidationResult:
    """Validate a complete PPT instruction JSON.

    Tests ALL elements at once, collecting every error.
    """
    logger.info("Validating PPT instruction: %d slide(s)", len(data.get("slides", [])))
    errors: list[dict] = []

    # ── 1) Pydantic structural validation ──
    try:
        instruction = PPTInstruction.model_validate(data)
    except Exception as exc:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            for err in exc.errors():
                loc = ".".join(str(x) for x in err["loc"])
                errors.append({"path": f"<root>.{loc}", "error": err["msg"]})
        else:
            errors.append({"path": "<root>", "error": str(exc)})
        logger.warning("Pydantic validation failed: %d error(s)", len(errors))
        return ValidationResult(is_valid=False, errors=errors)

    # ── 2) Cross-element checks ──
    for si, slide in enumerate(instruction.slides):
        for ei, el in enumerate(slide.elements):
            base_path = f"slides[{si}].elements[{ei}]"

            if el.type == "chart":
                _check_chart(el, base_path, errors)
            elif el.type == "table":
                _check_table(el, base_path, errors)
            elif el.type == "textbox":
                _check_textbox(el, base_path, errors)
            elif el.type == "shape":
                _check_shape(el, base_path, errors)
            elif el.type == "picture":
                _check_picture(el, base_path, errors)

    is_valid = len(errors) == 0
    if is_valid:
        logger.info("Validation PASSED: %d slide(s)", len(instruction.slides))
    else:
        logger.warning("Validation FAILED: %d error(s)", len(errors))
        for e in errors:
            logger.debug("  %s: %s", e["path"], e["error"])

    return ValidationResult(is_valid=is_valid, errors=errors, parsed=instruction)


def _check_chart(el: ChartElement, bp: str, errors: list[dict]) -> None:
    n = len(el.data.series)
    if n == 0:
        errors.append({"path": f"{bp}.data.series", "error": "chart needs >=1 series"})
    if el.style and el.style.series_colors:
        if len(el.style.series_colors) < n:
            errors.append({"path": f"{bp}.style.series_colors",
                           "error": f"series_colors ({len(el.style.series_colors)}) < series ({n})"})
    if "pie" in el.chart_type and n > 1:
        errors.append({"path": f"{bp}.chart_type",
                       "error": f"pie chart supports 1 series, got {n}"})


def _check_table(el: TableElement, bp: str, errors: list[dict]) -> None:
    for ci, cell in enumerate(el.cells):
        if cell.row >= el.rows:
            errors.append({"path": f"{bp}.cells[{ci}]", "error": f"row {cell.row} >= {el.rows}"})
        if cell.col >= el.cols:
            errors.append({"path": f"{bp}.cells[{ci}]", "error": f"col {cell.col} >= {el.cols}"})
    if el.merges:
        for mi, m in enumerate(el.merges):
            if m.from_row >= el.rows or m.to_row >= el.rows:
                errors.append({"path": f"{bp}.merges[{mi}]", "error": "merge row OOB"})
            if m.from_col >= el.cols or m.to_col >= el.cols:
                errors.append({"path": f"{bp}.merges[{mi}]", "error": "merge col OOB"})
            if m.from_row > m.to_row or m.from_col > m.to_col:
                errors.append({"path": f"{bp}.merges[{mi}]", "error": "merge from > to"})


def _check_textbox(el: TextboxElement, bp: str, errors: list[dict]) -> None:
    for bi, block in enumerate(el.content):
        if not block.paragraph.runs:
            errors.append({"path": f"{bp}.content[{bi}].paragraph.runs",
                           "error": "paragraph has no runs"})


def _check_shape(el: ShapeElement, bp: str, errors: list[dict]) -> None:
    if el.fill and el.fill.type == "gradient":
        if el.fill.gradient_angle is None and el.fill.gradient_stops is None:
            errors.append({"path": f"{bp}.fill",
                           "error": "gradient requires gradient_angle or gradient_stops"})


def _check_picture(el: ImageElement, bp: str, errors: list[dict]) -> None:
    if not el.path:
        errors.append({"path": f"{bp}.path", "error": "picture path is empty"})
