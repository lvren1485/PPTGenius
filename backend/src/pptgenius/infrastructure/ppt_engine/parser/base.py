"""Core Pydantic models and central validator for PPT instruction JSON.

validator: ``validate_instruction(dict) → ValidationResult``
  - Tests ALL objects at once, collects every error.
  - Returns (is_valid, errors_by_path).

The LLM receives a single error report with all problems, minimizing retry rounds.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .shapes import ALL_SHAPE_KEYS


# ═══════════════════════════════════════════════════════════════════
# Element sub-models
# ═══════════════════════════════════════════════════════════════════

class FontSpec(BaseModel):
    name: str | None = None
    size: int | None = None           # pt
    bold: bool | None = None
    italic: bool | None = None
    color: str | None = None          # '#1a73e8' or '1a73e8'
    underline: str | None = None      # 'none'|'single'|'double'|'wavy'
    strikethrough: str | None = None  # 'single'|'double'
    small_caps: bool | None = None
    all_caps: bool | None = None
    kerning_pt: float | None = None
    shadow: FontShadow | None = None
    glow: FontGlow | None = None

    @field_validator("color")
    @classmethod
    def _check_color(cls, v: str | None) -> str | None:
        if v is None:
            return v
        h = v.lstrip("#")
        if len(h) != 6:
            raise ValueError(f"color must be 6-digit hex, got '{v}'")
        int(h, 16)  # will raise if invalid hex
        return h


class FontShadow(BaseModel):
    blur_pt: float = 3.0
    offset_pt: float = 1.5
    angle_deg: float = 315.0
    color: str = "000000"
    alpha_pct: float = 40.0


class FontGlow(BaseModel):
    radius_pt: float = 8.0
    color: str = "1a73e8"
    alpha_pct: float = 60.0


class RunSpec(BaseModel):
    text: str
    font: FontSpec | None = None


class ParagraphSpec(BaseModel):
    alignment: Literal["left", "center", "right", "justify"] = "left"
    level: int = Field(default=0, ge=0, le=8)
    space_before_pt: int | None = None
    space_after_pt: int | None = None
    runs: list[RunSpec] = []


class ContentBlock(BaseModel):
    """One paragraph inside a textbox."""
    paragraph: ParagraphSpec


class Position(BaseModel):
    left: float = Field(ge=0)
    top: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float | None = None  # optional for picture (aspect-ratio auto-height)


class LineStyle(BaseModel):
    color: str | None = None
    width_pt: float = 1.0
    dash: Literal["solid", "dash", "dot", "dash_dot"] | None = None


class FillStyle(BaseModel):
    type: Literal["solid", "gradient", "no_fill", "picture"] = "solid"
    color: str | None = None  # for solid
    gradient_angle: float | None = None  # for gradient (0=left→right)
    gradient_stops: list[GradientStop] | None = None  # extra stops


class GradientStop(BaseModel):
    position: float = Field(ge=0.0, le=1.0)
    color: str


# ═══════════════════════════════════════════════════════════════════
# Element types
# ═══════════════════════════════════════════════════════════════════

class TextboxElement(BaseModel):
    type: Literal["textbox"]
    position: Position
    content: list[ContentBlock]
    fill: FillStyle | None = None
    line: LineStyle | None = None
    rotation: float | None = None


class ChartSeries(BaseModel):
    name: str
    values: list[float]


class ChartData(BaseModel):
    categories: list[str] = []
    series: list[ChartSeries]

    @field_validator("series")
    @classmethod
    def _check_series_lengths(cls, v: list[ChartSeries], info) -> list[ChartSeries]:
        categories_count = info.data.get("categories")
        if categories_count is not None:
            n_cats = len(categories_count)
            for i, s in enumerate(v):
                if len(s.values) != n_cats:
                    raise ValueError(
                        f"series[{i}].values length ({len(s.values)}) "
                        f"!= categories length ({n_cats})"
                    )
        return v


CHART_TYPES = frozenset({
    "column_clustered", "column_stacked", "column_stacked_100",
    "bar_clustered", "bar_stacked", "bar_stacked_100",
    "line", "line_markers", "line_stacked", "line_stacked_100",
    "pie", "pie_exploded",
    "doughnut", "doughnut_exploded",
    "area", "area_stacked", "area_stacked_100",
    "scatter", "scatter_lines", "scatter_lines_no_markers",
    "radar", "radar_filled", "radar_markers",
    "bubble",
})


class ChartStyle(BaseModel):
    has_legend: bool = True
    legend_position: Literal["bottom", "right", "left", "top"] = "bottom"
    has_data_labels: bool = False
    data_label_position: str | None = None
    series_colors: list[str] | None = None  # hex per series
    chart_area_fill: str | None = None  # hex or 'none'
    plot_area_fill: str | None = None
    title_font_size: int | None = None
    axis_font_size: int | None = None


class ChartElement(BaseModel):
    type: Literal["chart"]
    chart_type: str
    position: Position
    data: ChartData
    style: ChartStyle | None = None
    title: str | None = None

    @field_validator("chart_type")
    @classmethod
    def _check_chart_type(cls, v: str) -> str:
        if v not in CHART_TYPES:
            raise ValueError(f"unknown chart_type '{v}'. valid: {sorted(CHART_TYPES)}")
        return v


class CellSpec(BaseModel):
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    text: str
    font: FontSpec | None = None


class MergeSpec(BaseModel):
    from_row: int; from_col: int  # noqa: E701
    to_row: int; to_col: int      # noqa: E701


class TableHeader(BaseModel):
    row: int = 0
    fill: str
    font_color: str = "ffffff"
    font_bold: bool = True
    font_size: int = 14


class TableStyle(BaseModel):
    border_color: str = "e0e0e0"
    border_width_pt: float = 0.5
    stripe_even: str | None = None  # hex
    stripe_odd: str | None = None


class TableElement(BaseModel):
    type: Literal["table"]
    position: Position
    rows: int = Field(gt=0)
    cols: int = Field(gt=0)
    col_widths: list[float] | None = None
    cells: list[CellSpec] = []
    merges: list[MergeSpec] | None = None
    header: TableHeader | None = None
    style: TableStyle | None = None

    @field_validator("col_widths")
    @classmethod
    def _check_col_widths(cls, v: list[float] | None, info) -> list[float] | None:
        if v is not None:
            cols = info.data.get("cols")
            if cols is not None and len(v) != cols:
                raise ValueError(f"col_widths length {len(v)} != cols {cols}")
        return v


class ImageElement(BaseModel):
    type: Literal["picture"]
    position: Position
    path: str
    fit: Literal["aspect", "stretch", "crop"] = "aspect"


SHAPE_KEYS = frozenset(ALL_SHAPE_KEYS)


class ShapeElement(BaseModel):
    type: Literal["shape"]
    shape_type: str
    position: Position
    fill: FillStyle | None = None
    line: LineStyle | None = None
    text: list[ContentBlock] | None = None  # optional text in shape
    rotation: float | None = None

    @field_validator("shape_type")
    @classmethod
    def _check_shape_type(cls, v: str) -> str:
        if v not in SHAPE_KEYS:
            raise ValueError(
                f"unknown shape_type '{v}'. See MSO_SHAPE catalog. "
                f"Use a key from {sorted(SHAPE_KEYS)[:20]}..."
            )
        return v


# ═══════════════════════════════════════════════════════════════════
# Slide & Instruction top-level
# ═══════════════════════════════════════════════════════════════════

LAYOUT_NAMES = frozenset({
    "title_slide", "content_bullet", "content_chart", "content_table",
    "two_column", "image_text", "ending", "blank",
})

Element = TextboxElement | ChartElement | TableElement | ImageElement | ShapeElement


class SlideSpec(BaseModel):
    layout: str = "blank"
    color_scheme: dict | None = None
    elements: list[Element] = []

    @field_validator("layout")
    @classmethod
    def _check_layout(cls, v: str) -> str:
        if v not in LAYOUT_NAMES:
            raise ValueError(f"unknown layout '{v}'. valid: {sorted(LAYOUT_NAMES)}")
        return v


class MetaSpec(BaseModel):
    template_name: str | None = None
    color_scheme_name: str | None = None
    slide_width: float = 13.333
    slide_height: float = 7.5
    language: str = "zh"


class PPTInstruction(BaseModel):
    """Root model for the complete PPT instruction JSON."""
    meta: MetaSpec = MetaSpec()
    slides: list[SlideSpec] = Field(min_length=1)
