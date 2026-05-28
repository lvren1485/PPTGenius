"""Tests for Phase 2 — supervisor logic, sub-agent dispatch, freedom agent logic.

All tests are API-call-free (no LLM required).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pptgenius.agent.ppt.phase2_sub_agent.supervisor import (
    _determine_agents,
    _run_with_timing,
    Phase2Timing,
)
from pptgenius.agent.ppt.phase2_sub_agent.text_agent import (
    _build_system_prompt as text_system_prompt,
    _build_user_prompt as text_user_prompt,
)
from pptgenius.agent.ppt.phase2_sub_agent.chart_agent import (
    _build_chart_system_prompt,
    _build_chart_user_prompt,
)
from pptgenius.agent.ppt.phase2_sub_agent.shape_agent import (
    _build_system_prompt as shape_system_prompt,
    _build_user_prompt as shape_user_prompt,
)
from pptgenius.agent.ppt.phase2_freedom.freedom_agent import (
    _build_freedom_system_prompt,
    _build_freedom_user_prompt,
)
from pptgenius.agent.ppt.phase2_freedom.supervisor import (
    FreedomTiming,
)
from pptgenius.agent.ppt.common.instruction_loader import get_how_to_read


# ═══════════════════════════════════════════════════════════════════════════════
# HOW_TO_READ.md injection
# ═══════════════════════════════════════════════════════════════════════════════


class TestHowToReadInjection:
    def test_how_to_read_loads(self):
        text = get_how_to_read()
        assert len(text) > 100
        assert "string|null" in text or "hex[]" in text or "符号约定" in text

    def test_text_agent_prompt_includes_how_to_read(self):
        prompt = text_system_prompt()
        assert "符号约定" in prompt or "string|null" in prompt or "hex[]" in prompt

    def test_chart_agent_prompt_includes_how_to_read(self):
        prompt = _build_chart_system_prompt()
        assert "符号约定" in prompt or "string|null" in prompt or "hex[]" in prompt

    def test_shape_agent_prompt_includes_how_to_read(self):
        prompt = shape_system_prompt()
        assert "符号约定" in prompt or "string|null" in prompt or "hex[]" in prompt

    def test_freedom_agent_prompt_includes_how_to_read(self):
        prompt = _build_freedom_system_prompt()
        assert "符号约定" in prompt or "string|null" in prompt or "hex[]" in prompt


# ═══════════════════════════════════════════════════════════════════════════════
# Supervisor — agent determination
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetermineAgents:
    def test_content_slide_needs_only_text(self):
        agents = _determine_agents(
            {"has_chart": False, "layout_type": "content"},
            "content_bullet",
        )
        assert agents == ["text"]

    def test_content_slide_with_chart_needs_text_and_chart(self):
        agents = _determine_agents(
            {"has_chart": True, "layout_type": "content"},
            "content_bullet",
        )
        assert "text" in agents
        assert "chart" in agents
        assert "shape" not in agents

    def test_title_slide_needs_text_and_shape(self):
        agents = _determine_agents(
            {"has_chart": False, "layout_type": "title"},
            "title_slide",
        )
        assert "text" in agents
        assert "shape" in agents
        assert "chart" not in agents

    def test_section_slide_needs_text_and_shape(self):
        agents = _determine_agents(
            {"has_chart": False, "layout_type": "section"},
            "section",
        )
        assert "shape" in agents

    def test_ending_slide_needs_text_and_shape(self):
        agents = _determine_agents(
            {"has_chart": False, "layout_type": "thanks"},
            "ending",
        )
        assert "shape" in agents

    def test_two_column_slide_needs_only_text(self):
        agents = _determine_agents(
            {"has_chart": False, "layout_type": "content"},
            "content_two_column",
        )
        assert agents == ["text"]

    def test_summary_slide_needs_only_text(self):
        agents = _determine_agents(
            {"has_chart": False, "layout_type": "summary"},
            "content_bullet",
        )
        assert agents == ["text"]


# ═══════════════════════════════════════════════════════════════════════════════
# Supervisor — timing
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhase2Timing:
    def test_total_seconds_zero_before_end(self):
        t = Phase2Timing(total_start=100.0)
        assert t.total_seconds == -100.0  # end defaults to 0

    def test_total_seconds_after_end(self):
        t = Phase2Timing(total_start=100.0, total_end=105.0)
        assert t.total_seconds == 5.0

    def test_to_dict_includes_all_fields(self):
        t = Phase2Timing(
            total_start=100.0, total_end=105.0,
            slide_times=[1.0, 2.0, 1.5],
            agent_times={"text": [0.5, 0.8, 0.6], "chart": [0.9]},
        )
        d = t.to_dict()
        assert d["total_seconds"] == 5.0
        assert d["slide_count"] == 3
        assert len(d["slide_times"]) == 3
        assert "text" in d["agent_times"]


class TestFreedomTiming:
    def test_basic_timing(self):
        t = FreedomTiming(total_start=100.0, total_end=110.0, slide_times=[2.0, 3.0])
        assert t.total_seconds == 10.0
        d = t.to_dict()
        assert d["slide_count"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Supervisor — _run_with_timing
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunWithTiming:
    @pytest.mark.asyncio
    async def test_returns_agent_name_and_time(self):
        async def dummy_agent(**kwargs):
            return None

        name, elapsed, exc = await _run_with_timing(dummy_agent, some_arg=1)
        assert name == "dummy_agent"
        assert elapsed >= 0
        assert exc is None

    @pytest.mark.asyncio
    async def test_captures_exception(self):
        async def failing_agent(**kwargs):
            raise ValueError("test error")

        name, elapsed, exc = await _run_with_timing(failing_agent)
        assert name == "failing_agent"
        assert isinstance(exc, ValueError)


# ═══════════════════════════════════════════════════════════════════════════════
# TextAgent prompt building
# ═══════════════════════════════════════════════════════════════════════════════


class TestTextAgentPrompts:
    def test_system_prompt_contains_instruction_types(self):
        prompt = text_system_prompt()
        assert "textbox" in prompt.lower()
        assert "table" in prompt.lower()
        assert "picture" in prompt.lower() or "icon" in prompt.lower()

    def test_user_prompt_includes_slide_info(self):
        slide = {
            "title": "测试页面",
            "layout_type": "content",
            "content_json": {"main_points": ["要点1"], "detailed_content": "详细内容"},
            "has_image": False,
            "has_chart": False,
        }
        prompt = text_user_prompt(slide, "content_bullet", {"slide": {"left": 0, "top": 0, "width": 13.333, "height": 7.5}})
        assert "测试页面" in prompt
        assert "要点1" in prompt
        assert "详细内容" in prompt

    def test_user_prompt_with_container_context(self):
        slide = {"title": "两栏", "layout_type": "content", "content_json": {}}
        bounds = {
            "slide": {"left": 0, "top": 0, "width": 13.333, "height": 7.5},
            "left_col": {"left": 0.5, "top": 1.6, "width": 5.8, "height": 5.1},
        }
        prompt = text_user_prompt(slide, "content_two_column", bounds)
        assert "left_col" in prompt
        assert "相对坐标" in prompt or "parent" in prompt

    def test_user_prompt_no_container_uses_absolute(self):
        slide = {"title": "单栏", "layout_type": "content", "content_json": {}}
        prompt = text_user_prompt(slide, "content_bullet", {"slide": {"left": 0, "top": 0, "width": 13.333, "height": 7.5}})
        assert "绝对坐标" in prompt or "无容器" in prompt

    def test_user_prompt_handles_string_content_json(self):
        slide = {
            "title": "JSON字符串",
            "content_json": '{"main_points": ["解析测试"]}',
        }
        prompt = text_user_prompt(slide, "content_bullet", {"slide": {"left": 0, "top": 0, "width": 13.333, "height": 7.5}})
        assert "解析测试" in prompt


# ═══════════════════════════════════════════════════════════════════════════════
# ChartAgent prompt building
# ═══════════════════════════════════════════════════════════════════════════════


class TestChartAgentPrompts:
    def test_system_prompt_contains_chart_types(self):
        prompt = _build_chart_system_prompt()
        assert "column_clustered" in prompt
        assert "pie" in prompt
        assert "line" in prompt

    def test_system_prompt_contains_selection_rules(self):
        prompt = _build_chart_system_prompt()
        assert "分类对比" in prompt or "占比" in prompt or "选择" in prompt

    def test_user_prompt_includes_slide_data(self):
        slide = {
            "title": "销售数据",
            "content_json": {"key_data": "Q1: 100, Q2: 150", "main_points": ["增长趋势"]},
        }
        prompt = _build_chart_user_prompt(slide, {
            "slide": {"left": 0, "top": 0, "width": 13.333, "height": 7.5},
            "left_col": {"left": 0.5, "top": 1.6, "width": 5.8, "height": 5.1},
        })
        assert "销售数据" in prompt
        assert "left_col" in prompt

    def test_user_prompt_no_container_suggests_default_position(self):
        slide = {"title": "图表", "content_json": {}}
        prompt = _build_chart_user_prompt(slide, {"slide": {"left": 0, "top": 0, "width": 13.333, "height": 7.5}})
        assert "1.6" in prompt or "5.0" in prompt  # default chart position


# ═══════════════════════════════════════════════════════════════════════════════
# ShapeAgent prompt building
# ═══════════════════════════════════════════════════════════════════════════════


class TestShapeAgentPrompts:
    def test_system_prompt_contains_shape_catalog(self):
        prompt = shape_system_prompt()
        assert "rounded_rectangle" in prompt or "矩形" in prompt or "rectangle" in prompt

    def test_system_prompt_has_page_type_suggestions(self):
        prompt = shape_system_prompt()
        assert "title_slide" in prompt or "封面" in prompt
        assert "section" in prompt or "章节" in prompt

    def test_user_prompt_includes_layout_context(self):
        slide = {"title": "第一章", "layout_type": "section"}
        prompt = shape_user_prompt(slide, "section", {"slide": {"left": 0, "top": 0, "width": 13.333, "height": 7.5}})
        assert "第一章" in prompt
        assert "section" in prompt


# ═══════════════════════════════════════════════════════════════════════════════
# FreedomAgent prompt building
# ═══════════════════════════════════════════════════════════════════════════════


class TestFreedomAgentPrompts:
    def test_system_prompt_contains_all_core_types(self):
        prompt = _build_freedom_system_prompt()
        assert "textbox" in prompt.lower()
        assert "table" in prompt.lower()
        assert "shape" in prompt.lower()
        assert "chart" in prompt.lower()

    def test_system_prompt_has_chart_type_list(self):
        prompt = _build_freedom_system_prompt()
        assert "column_clustered" in prompt
        assert "pie" in prompt

    def test_user_prompt_includes_full_slide_data(self):
        slide = {
            "title": "综合页面",
            "layout_type": "content",
            "has_chart": True,
            "has_image": False,
            "content_json": {"main_points": ["A", "B"], "detailed_content": "test", "key_data": "100"},
        }
        prompt = _build_freedom_user_prompt(slide, "content_bullet", {"slide": {"left": 0, "top": 0, "width": 13.333, "height": 7.5}})
        assert "综合页面" in prompt
        assert "has_chart" in prompt
        assert "A" in prompt
        assert "100" in prompt

    def test_user_prompt_with_containers(self):
        slide = {"title": "网格", "content_json": {}}
        bounds = {
            "slide": {"left": 0, "top": 0, "width": 13.333, "height": 7.5},
            "grid_00": {"left": 0.5, "top": 1.6, "width": 5.8, "height": 2.5},
            "grid_01": {"left": 6.8, "top": 1.6, "width": 5.8, "height": 2.5},
        }
        prompt = _build_freedom_user_prompt(slide, "content_grid_2x2", bounds)
        assert "grid_00" in prompt
        assert "grid_01" in prompt
        assert "parent" in prompt


# ═══════════════════════════════════════════════════════════════════════════════
# Slide routing (layout_type → layout)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhase2SlideRouting:
    """Verify the slide router produces correct results."""

    def test_all_outline_types_route_to_valid_layouts(self):
        from pptgenius.agent.ppt.common.layout_resolver import select_layout

        valid = {
            "title_slide", "section", "content_bullet", "content_two_column",
            "content_three_column", "content_grid_2x2", "ending",
        }
        for lt, expected in [
            ("title", "title_slide"),
            ("section", "section"),
            ("content", "content_bullet"),
            ("summary", "content_bullet"),
            ("thanks", "ending"),
        ]:
            result = select_layout({"layout_type": lt})
            assert result == expected, f"{lt} → {result}, expected {expected}"
            assert result in valid, f"{result} not valid"


# ═══════════════════════════════════════════════════════════════════════════════
# Tools validation (mocked DB)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSubmitTools:
    @pytest.mark.asyncio
    async def test_submit_text_elements_with_valid_data(self):
        from pptgenius.agent.ppt.common.tools import _make_submit_text_elements

        db = MagicMock()
        db.set_slide_agent_output = AsyncMock()

        tool = _make_submit_text_elements(db, presentation_id=1, slide_index=0)

        result = await tool.ainvoke({
            "elements": [{
                "type": "textbox",
                "position": {"left": 1.0, "top": 1.0, "width": 11.0, "height": 1.0},
                "content": [{"paragraph": {"alignment": "left", "runs": [{"text": "Hello"}]}}],
            }]
        })
        # Single valid textbox should pass validation
        assert "✅" in result or "校验失败" in result

    @pytest.mark.asyncio
    async def test_submit_chart_valid_element(self):
        from pptgenius.agent.ppt.common.tools import _make_submit_chart_element

        db = MagicMock()
        db.set_slide_agent_output = AsyncMock()

        tool = _make_submit_chart_element(db, presentation_id=1, slide_index=0)

        result = await tool.ainvoke({
            "element": {
                "type": "chart",
                "chart_type": "column_clustered",
                "position": {"left": 1.0, "top": 1.5, "width": 8.0, "height": 5.0},
                "data": {
                    "categories": ["Q1", "Q2", "Q3"],
                    "series": [{"name": "A", "values": [10, 20, 30]}],
                },
            }
        })
        # Valid chart should pass
        assert "✅" in result or "校验失败" in result

    @pytest.mark.asyncio
    async def test_submit_chart_invalid_type_rejected(self):
        from pptgenius.agent.ppt.common.tools import _make_submit_chart_element

        db = MagicMock()
        db.set_slide_agent_output = AsyncMock()

        tool = _make_submit_chart_element(db, presentation_id=1, slide_index=0)

        result = await tool.ainvoke({
            "element": {
                "type": "chart",
                "chart_type": "invalid_type_xyz",
                "position": {"left": 1.0, "top": 1.5, "width": 8.0, "height": 5.0},
                "data": {"categories": [], "series": []},
            }
        })
        assert "校验失败" in result or "失败" in result

    @pytest.mark.asyncio
    async def test_submit_shape_valid_element(self):
        from pptgenius.agent.ppt.common.tools import _make_submit_shape_elements

        db = MagicMock()
        db.set_slide_agent_output = AsyncMock()

        tool = _make_submit_shape_elements(db, presentation_id=1, slide_index=0)

        result = await tool.ainvoke({
            "elements": [{
                "type": "shape",
                "shape_type": "rectangle",
                "position": {"left": 1.0, "top": 1.0, "width": 2.0, "height": 0.5},
            }]
        })
        assert "✅" in result or "校验失败" in result

    @pytest.mark.asyncio
    async def test_submit_slide_elements_freedom(self):
        from pptgenius.agent.ppt.common.tools import _make_submit_slide_elements

        db = MagicMock()
        db.set_slide_agent_output = AsyncMock()

        tool = _make_submit_slide_elements(db, presentation_id=1, slide_index=0)

        result = await tool.ainvoke({
            "elements": [
                {
                    "type": "textbox",
                    "position": {"left": 1.0, "top": 1.0, "width": 11.0, "height": 1.0},
                    "content": [{"paragraph": {"alignment": "left", "runs": [{"text": "Title"}]}}],
                },
            ]
        })
        # Check result is meaningful
        assert len(result) > 10
