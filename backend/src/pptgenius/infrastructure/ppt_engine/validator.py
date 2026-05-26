"""Central validator for PPT instruction JSON — element-level parallel.

Protocol:
    validate_elements(list[dict]) → ValidationResult    # flat element list
    validate_instruction(dict)    → ValidationResult    # full PPTInstruction

Design: each element is validated independently. A bad shape_type on element 3
does NOT prevent cross-element checks on element 1, 2, 4 of the same slide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from .parser.base import (
    PPTInstruction,
    SlideSpec,
    ChartElement, TableElement, TextboxElement, ImageElement, ShapeElement,
)

logger = logging.getLogger("ppt_engine.validator")

# ── Element model registry ──
_ELEMENT_MODELS = {
    "textbox": TextboxElement,
    "chart":   ChartElement,
    "table":   TableElement,
    "picture": ImageElement,
    "shape":   ShapeElement,
}


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[dict] = field(default_factory=list)
    parsed: PPTInstruction | None = None


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def validate_elements(elements: list[dict]) -> ValidationResult:
    """Validate a flat list of element dicts. Each element independently.

    Use this when the agent produces just elements (e.g. chart_agent output),
    not a complete PPTInstruction.
    """
    logger.info("Validating %d element(s)", len(elements))
    errors = _validate_element_list(elements, "")
    is_valid = len(errors) == 0
    if is_valid:
        logger.info("Element validation PASSED (%d elements)", len(elements))
    else:
        logger.warning("Element validation FAILED: %d error(s)", len(errors))
        for e in errors[:20]:
            logger.debug("  %s: %s", e["path"], e["error"])
    return ValidationResult(is_valid=is_valid, errors=errors)


def validate_instruction(data: dict[str, Any]) -> ValidationResult:
    """Validate a complete PPT instruction JSON (element-level parallel)."""
    logger.info("Validating PPT instruction: %d slide(s)", len(data.get("slides", [])))
    errors: list[dict] = []

    # ── Meta validation ──
    try:
        PPTInstruction.model_validate(data)
    except Exception as exc:
        if isinstance(exc, ValidationError):
            for err in exc.errors():
                loc = ".".join(str(x) for x in err["loc"])
                if not any(prefix in loc for prefix in ("slides.",)):
                    errors.append({"path": f"<root>.{loc}", "error": err["msg"]})

    # ── Per-element validation (ALL slides, ALL elements independently) ──
    for si, slide_data in enumerate(data.get("slides", [])):
        elements_data = slide_data.get("elements", [])
        for ei, el_data in enumerate(elements_data):
            prefix = f"slides[{si}].elements[{ei}]"
            el_errors = _validate_single_element(el_data, prefix)
            errors.extend(el_errors)

        # Slide-level structural errors
        try:
            SlideSpec.model_validate(slide_data)
        except Exception as exc:
            if isinstance(exc, ValidationError):
                for err in exc.errors():
                    loc = ".".join(str(x) for x in err["loc"])
                    # Only slide-level errors (not element errors — already handled above)
                    if not loc.startswith("elements"):
                        errors.append({"path": f"slides[{si}].{loc}", "error": err["msg"]})

    is_valid = len(errors) == 0
    if is_valid:
        logger.info("Validation PASSED: %d slide(s)", len(data.get("slides", [])))
        parsed = PPTInstruction.model_validate(data) if not errors else None
        return ValidationResult(is_valid=True, errors=[], parsed=parsed)
    else:
        logger.warning("Validation FAILED: %d error(s)", len(errors))
        for e in errors[:20]:
            logger.debug("  %s: %s", e["path"], e["error"])
        if len(errors) > 20:
            logger.debug("  ... and %d more", len(errors) - 20)
        return ValidationResult(is_valid=False, errors=errors)


# ═══════════════════════════════════════════════════════════════════════
# Single-element validation (Pydantic + cross-element)
# ═══════════════════════════════════════════════════════════════════════

def _validate_element_list(elements: list[dict], prefix: str) -> list[dict]:
    errors: list[dict] = []
    for ei, el_data in enumerate(elements):
        p = f"{prefix}[{ei}]" if prefix else f"elements[{ei}]"
        errors.extend(_validate_single_element(el_data, p))
    return errors


def _validate_single_element(el_data: dict, path: str) -> list[dict]:
    """Validate one element dict independently. Returns error list."""
    errors: list[dict] = []
    el_type = el_data.get("type", "?")

    model = _ELEMENT_MODELS.get(el_type)
    if model is None:
        errors.append({
            "path": f"{path}.type",
            "error": f"unknown element type '{el_type}'. valid: {sorted(_ELEMENT_MODELS.keys())}"
        })
        return errors

    # Pydantic structural validation
    try:
        el = model.model_validate(el_data)
    except Exception as exc:
        if isinstance(exc, ValidationError):
            for err in exc.errors():
                loc = ".".join(str(x) for x in err["loc"])
                errors.append({"path": f"{path}.{loc}", "error": err["msg"]})
        else:
            errors.append({"path": path, "error": str(exc)})
        return errors  # if struct is broken, skip cross-element checks for this element

    # Cross-element semantic checks
    _check_semantic(el, path, errors)
    return errors


def _check_semantic(el, path: str, errors: list[dict]) -> None:
    """Cross-element semantic validation."""
    if el.type == "chart":
        _check_chart(el, path, errors)
    elif el.type == "table":
        _check_table(el, path, errors)
    elif el.type == "textbox":
        _check_textbox(el, path, errors)
    elif el.type == "shape":
        _check_shape(el, path, errors)
    elif el.type == "picture":
        _check_picture(el, path, errors)


# ═══════════════════════════════════════════════════════════════════════
# Per-type semantic checks
# ═══════════════════════════════════════════════════════════════════════

def _check_chart(el: ChartElement, path: str, errors: list[dict]) -> None:
    if el.is_xy or el.is_bubble:
        n = len(el.data.series)  # type: ignore[attr-defined]
        if n == 0:
            errors.append({"path": f"{path}.data.series", "error": "chart needs >=1 series"})
        for si, s in enumerate(el.data.series):
            if len(s.points) == 0:
                errors.append({"path": f"{path}.data.series[{si}].points",
                               "error": f"series '{s.name}' has no points"})
        if el.style and el.style.series_colors:
            if len(el.style.series_colors) < n:
                errors.append({"path": f"{path}.style.series_colors",
                               "error": f"series_colors ({len(el.style.series_colors)}) < series ({n})"})
        return

    n = len(el.data.series)
    if n == 0:
        errors.append({"path": f"{path}.data.series", "error": "chart needs >=1 series"})
    if el.style and el.style.series_colors:
        if len(el.style.series_colors) < n:
            errors.append({"path": f"{path}.style.series_colors",
                           "error": f"series_colors ({len(el.style.series_colors)}) < series ({n})"})
    if "pie" in el.chart_type and n > 1:
        errors.append({"path": f"{path}.chart_type",
                       "error": f"pie chart supports 1 series, got {n}"})
    if "doughnut" in el.chart_type and n > 1:
        errors.append({"path": f"{path}.chart_type",
                       "error": f"doughnut chart supports 1 series, got {n}"})


def _check_table(el: TableElement, path: str, errors: list[dict]) -> None:
    for ci, cell in enumerate(el.cells):
        if cell.row >= el.rows:
            errors.append({"path": f"{path}.cells[{ci}]", "error": f"row {cell.row} >= {el.rows}"})
        if cell.col >= el.cols:
            errors.append({"path": f"{path}.cells[{ci}]", "error": f"col {cell.col} >= {el.cols}"})
    if el.merges:
        for mi, m in enumerate(el.merges):
            if m.from_row >= el.rows or m.to_row >= el.rows:
                errors.append({"path": f"{path}.merges[{mi}]", "error": "merge row OOB"})
            if m.from_col >= el.cols or m.to_col >= el.cols:
                errors.append({"path": f"{path}.merges[{mi}]", "error": "merge col OOB"})
            if m.from_row > m.to_row or m.from_col > m.to_col:
                errors.append({"path": f"{path}.merges[{mi}]", "error": "merge from > to"})


def _check_textbox(el: TextboxElement, path: str, errors: list[dict]) -> None:
    for bi, block in enumerate(el.content):
        if not block.paragraph.runs:
            errors.append({"path": f"{path}.content[{bi}].paragraph.runs",
                           "error": "paragraph has no runs"})


def _check_shape(el: ShapeElement, path: str, errors: list[dict]) -> None:
    if el.fill and el.fill.type == "gradient":
        if el.fill.gradient_angle is None and el.fill.gradient_stops is None:
            errors.append({"path": f"{path}.fill",
                           "error": "gradient requires gradient_angle or gradient_stops"})


def _check_picture(el: ImageElement, path: str, errors: list[dict]) -> None:
    if not el.path:
        errors.append({"path": f"{path}.path", "error": "picture path is empty"})
