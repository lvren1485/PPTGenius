"""PPT common tools — icon search, instruction reading.  No DB access."""

from __future__ import annotations

import json

from langchain_core.tools import tool

from pptgenius.infrastructure.ppt_engine.icon_search import search_icons as _search_icons

from .instruction_loader import get_instruction, list_chart_instructions


def make_search_icons():
    @tool
    async def search_icons(query: str, top_k: int = 5) -> str:
        """Search Tabler icons (5000+ MIT-licensed) by keyword.

        Returns top-k matching icon names with categories. Use for decorative icons.
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


def make_read_instruction():
    @tool
    async def read_instruction(filename: str) -> str:
        """Read a PPT instruction file to learn the JSON schema for an element type.

        Args:
            filename: Relative path, e.g. "textbox.json", "table.json",
                "chart/column.json", "shared/position.json"
        """
        try:
            data = get_instruction(filename)
            return json.dumps(data, ensure_ascii=False, indent=2)
        except FileNotFoundError:
            return f"指令文件 '{filename}' 不存在。"
        except Exception as exc:
            return f"读取指令文件失败: {exc}"

    return read_instruction


def make_read_chart_instruction():
    @tool
    async def read_chart_instruction(chart_type: str) -> str:
        """Read a chart instruction file by chart type.

        Args:
            chart_type: e.g. column_clustered, bar_stacked, line, pie, doughnut, radar
        """
        _MAP = {
            "column": "chart/column.json", "column_clustered": "chart/column.json",
            "column_stacked": "chart/column.json", "column_stacked_100": "chart/column.json",
            "bar": "chart/bar.json", "bar_clustered": "chart/bar.json",
            "bar_stacked": "chart/bar.json", "bar_stacked_100": "chart/bar.json",
            "line": "chart/line.json", "line_markers": "chart/line.json",
            "line_stacked": "chart/line.json", "line_stacked_100": "chart/line.json",
            "pie": "chart/pie.json", "pie_exploded": "chart/pie.json",
            "doughnut": "chart/pie.json", "doughnut_exploded": "chart/pie.json",
            "area": "chart/area.json", "area_stacked": "chart/area.json",
            "area_stacked_100": "chart/area.json",
            "scatter": "chart/scatter.json", "scatter_lines": "chart/scatter.json",
            "scatter_lines_no_markers": "chart/scatter.json",
            "radar": "chart/radar.json", "radar_filled": "chart/radar.json",
            "radar_markers": "chart/radar.json", "bubble": "chart/bubble.json",
        }
        filename = _MAP.get(chart_type.lower())
        if not filename:
            available = [c["chart_type"] for c in list_chart_instructions()]
            return f"未知图表类型 '{chart_type}'。可用: {', '.join(available)}"

        try:
            data = get_instruction(filename)
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as exc:
            return f"读取图表指令失败: {exc}"

    return read_chart_instruction
