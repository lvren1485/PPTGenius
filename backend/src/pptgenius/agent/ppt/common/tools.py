"""Shared tools for PPT sub-agents — icon search, instruction reading, validation."""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.ppt_engine.icon_search import search_icons as _search_icons
from pptgenius.infrastructure.ppt_engine.validator import validate_elements

from .instruction_loader import get_instruction

_log = logging.getLogger("pptgenius.agent.ppt.tools")


# ── icon search ────────────────────────────────────────────────────────────────


def _make_search_icons():
    @tool
    async def search_icons(query: str, top_k: int = 5) -> str:
        """Search the Tabler icon library (5000+ MIT-licensed icons) by keyword.

        Returns top-k matching icon names with categories and scores.
        Use this to find decorative icons for slides.
        Example: search_icons("growth chart") → chart-line, trending-up, ...
        """
        results = _search_icons(query, top_k)
        if not results:
            return "未找到匹配的图标。尝试更通用的关键词如 'data', 'team', 'chart'。"
        items = []
        for r in results:
            items.append(
                f"- **{r['name']}** (category={r.get('category', '')}, "
                f"tags={r.get('tags', [])[:3]}, score={r['score']})"
            )
        return "\n".join(items)

    return search_icons


# ── instruction reader ─────────────────────────────────────────────────────────


def _make_read_instruction():
    @tool
    async def read_instruction(filename: str) -> str:
        """Read a PPT instruction file to learn the JSON schema for an element type.

        Parameters
        ----------
        filename : str — Relative path from instructions/, e.g.:
            "textbox.json", "table.json", "shape.json", "chart/column.json",
            "shared/position.json", "shared/font.json", "shared/fill.json",
            "shared/line.json", "picture.json", "background.json"
        """
        try:
            data = get_instruction(filename)
            return json.dumps(data, ensure_ascii=False, indent=2)
        except FileNotFoundError:
            return f"指令文件 '{filename}' 不存在。"
        except Exception as exc:
            return f"读取指令文件失败: {exc}"

    return read_instruction


def _make_read_chart_instruction():
    @tool
    async def read_chart_instruction(chart_type: str) -> str:
        """Read a chart instruction file by chart type.

        Parameters
        ----------
        chart_type : str — One of:
            column_clustered, column_stacked, column_stacked_100,
            bar_clustered, bar_stacked, bar_stacked_100,
            line, line_markers, line_stacked, line_stacked_100,
            pie, pie_exploded, doughnut, doughnut_exploded,
            area, area_stacked, area_stacked_100,
            scatter, scatter_lines, scatter_lines_no_markers,
            radar, radar_filled, radar_markers, bubble

        The tool automatically maps chart_type to the correct instruction file.
        """
        _MAP = {
            "column": "chart/column.json",
            "column_clustered": "chart/column.json",
            "column_stacked": "chart/column.json",
            "column_stacked_100": "chart/column.json",
            "bar": "chart/bar.json",
            "bar_clustered": "chart/bar.json",
            "bar_stacked": "chart/bar.json",
            "bar_stacked_100": "chart/bar.json",
            "line": "chart/line.json",
            "line_markers": "chart/line.json",
            "line_stacked": "chart/line.json",
            "line_stacked_100": "chart/line.json",
            "pie": "chart/pie.json",
            "pie_exploded": "chart/pie.json",
            "doughnut": "chart/pie.json",
            "doughnut_exploded": "chart/pie.json",
            "area": "chart/area.json",
            "area_stacked": "chart/area.json",
            "area_stacked_100": "chart/area.json",
            "scatter": "chart/scatter.json",
            "scatter_lines": "chart/scatter.json",
            "scatter_lines_no_markers": "chart/scatter.json",
            "radar": "chart/radar.json",
            "radar_filled": "chart/radar.json",
            "radar_markers": "chart/radar.json",
            "bubble": "chart/bubble.json",
        }
        filename = _MAP.get(chart_type.lower())
        if not filename:
            from .instruction_loader import list_chart_instructions
            available = [c["chart_type"] for c in list_chart_instructions()]
            return f"未知图表类型 '{chart_type}'。可用类型: {', '.join(available)}"

        try:
            data = get_instruction(filename)
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as exc:
            return f"读取图表指令失败: {exc}"

    return read_chart_instruction


# ── submit / validate tools ────────────────────────────────────────────────────


def _make_submit_text_elements(db: Database, presentation_id: int, slide_index: int):
    @tool
    async def submit_text_elements(elements: list[dict]) -> str:
        """Submit textbox, table, and picture elements.  Validates before saving.

        Parameters
        ----------
        elements : list[dict] — Each element has: type ("textbox"/"table"/"picture"),
            position (with optional parent), and type-specific fields.
        """
        result = validate_elements(elements)
        if not result.is_valid:
            error_details = "\n".join(
                f"  - [{e['path']}] {e['error']}" for e in result.errors[:10]
            )
            return (
                f"❌ 校验失败 ({len(result.errors)} 个错误):\n{error_details}\n"
                f"请根据错误修正后重新提交。"
            )

        # Save to agent_outputs
        await db.set_slide_agent_output(
            presentation_id=presentation_id,
            slide_index=slide_index,
            agent_name="text",
            output=elements,
        )
        return f"✅ 已保存 {len(elements)} 个文本/表格/图片元素。"

    return submit_text_elements


def _make_submit_chart_element(db: Database, presentation_id: int, slide_index: int):
    @tool
    async def submit_chart_element(element: dict) -> str:
        """Submit a single chart element.  Validates before saving.

        Parameters
        ----------
        element : dict — Chart element with type="chart", chart_type, position, data, style.
        """
        result = validate_elements([element])
        if not result.is_valid:
            error_details = "\n".join(
                f"  - [{e['path']}] {e['error']}" for e in result.errors[:10]
            )
            return (
                f"❌ 图表校验失败 ({len(result.errors)} 个错误):\n{error_details}\n"
                f"请根据错误修正后重新提交。比如检查 chart_type 是否合法、series 数量是否匹配等。"
            )

        await db.set_slide_agent_output(
            presentation_id=presentation_id,
            slide_index=slide_index,
            agent_name="chart",
            output=element,
        )
        return f"✅ 已保存图表元素 (type={element.get('chart_type')})。"

    return submit_chart_element


def _make_submit_shape_elements(db: Database, presentation_id: int, slide_index: int):
    @tool
    async def submit_shape_elements(elements: list[dict]) -> str:
        """Submit shape (decoration) elements.  Validates before saving.

        Parameters
        ----------
        elements : list[dict] — Each element has: type="shape", shape_type, position, fill, line, text.
            shape_type must be from shape_catalog.json (182 types).
        """
        result = validate_elements(elements)
        if not result.is_valid:
            error_details = "\n".join(
                f"  - [{e['path']}] {e['error']}" for e in result.errors[:10]
            )
            return (
                f"❌ 形状校验失败 ({len(result.errors)} 个错误):\n{error_details}\n"
                f"请根据错误修正后重新提交。"
            )

        await db.set_slide_agent_output(
            presentation_id=presentation_id,
            slide_index=slide_index,
            agent_name="shape",
            output=elements,
        )
        return f"✅ 已保存 {len(elements)} 个形状元素。"

    return submit_shape_elements


def _make_submit_slide_elements(db: Database, presentation_id: int, slide_index: int):
    """Freedom mode: submit all elements for a slide at once."""
    @tool
    async def submit_slide_elements(elements: list[dict]) -> str:
        """Submit ALL elements for this slide (textbox, chart, table, picture, shape).
        Freedom mode — one agent generates everything.  Validates all elements.

        Parameters
        ----------
        elements : list[dict] — Array of element objects.  Each element's type
            determines which schema it's validated against.
        """
        result = validate_elements(elements)
        if not result.is_valid:
            error_details = "\n".join(
                f"  - [{e['path']}] {e['error']}" for e in result.errors[:15]
            )
            return (
                f"❌ 校验失败 ({len(result.errors)} 个错误):\n{error_details}\n"
                f"请根据错误修正后重新提交。"
            )

        await db.set_slide_agent_output(
            presentation_id=presentation_id,
            slide_index=slide_index,
            agent_name="freedom",
            output=elements,
        )
        return f"✅ 已保存整页 {len(elements)} 个元素。"

    return submit_slide_elements
