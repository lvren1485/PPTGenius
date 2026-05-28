"""Tests for Phase 1 StyleAgent — tool creation, prompt loading, logic.

All tests are API-call-free.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pptgenius.agent.ppt.phase1_style import (
    _make_list_color_schemes,
    _make_get_color_scheme,
    _make_save_color_scheme,
    _make_list_layouts,
    _make_get_layout,
    _make_set_presentation_style,
    _load_prompt,
)


# ── prompt loading ────────────────────────────────────────────────────────────


class TestLoadPrompt:
    def test_prompt_file_exists_and_readable(self):
        prompt = _load_prompt()
        assert len(prompt) > 0
        assert "配色" in prompt or "color" in prompt.lower()


# ── list_color_schemes tool ───────────────────────────────────────────────────


class TestListColorSchemes:
    @pytest.mark.asyncio
    async def test_returns_empty_message_when_none(self):
        db = MagicMock()
        db.list_active_color_schemes = AsyncMock(return_value=[])
        tool = _make_list_color_schemes(db)
        result = await tool.ainvoke({"dummy": ""})
        assert "没有" in result

    @pytest.mark.asyncio
    async def test_returns_json_for_each_scheme(self):
        cs = MagicMock()
        cs.id = 1
        cs.name = "test_blue"
        cs.label = "测试蓝"
        cs.style_density = "moderate"
        cs.decoration_json = {"title_accent_bar": True}
        cs.colors_json = {"primary": "1a73e8", "bg": "ffffff"}

        db = MagicMock()
        db.list_active_color_schemes = AsyncMock(return_value=[cs])
        tool = _make_list_color_schemes(db)
        result = await tool.ainvoke({"dummy": ""})
        assert "test_blue" in result
        assert "测试蓝" in result
        assert "moderate" in result

    @pytest.mark.asyncio
    async def test_handles_missing_style_density(self):
        """Older color schemes may not have style_density."""
        cs = MagicMock()
        cs.id = 1
        cs.name = "old"
        cs.label = "旧方案"
        cs.colors_json = {"primary": "000000"}
        # simulate missing attribute
        del cs.style_density
        cs.decoration_json = {}

        db = MagicMock()
        db.list_active_color_schemes = AsyncMock(return_value=[cs])
        tool = _make_list_color_schemes(db)
        result = await tool.ainvoke({"dummy": ""})
        assert "old" in result


# ── get_color_scheme tool ─────────────────────────────────────────────────────


class TestGetColorScheme:
    @pytest.mark.asyncio
    async def test_returns_full_definition(self):
        cs = MagicMock()
        cs.id = 1
        cs.name = "test"
        cs.label = "测试"
        cs.style_density = "minimal"
        cs.decoration_json = {}
        cs.colors_json = {"primary": "ff0000"}
        cs.chart_colors_json = ["ff0000", "00ff00"]
        cs.fonts_json = {"title": {"name": "Arial", "size": 28}}

        db = MagicMock()
        db.get_color_scheme = AsyncMock(return_value=cs)
        tool = _make_get_color_scheme(db)
        result = await tool.ainvoke({"scheme_id": 1})
        data = json.loads(result)
        assert data["id"] == 1
        assert data["colors"]["primary"] == "ff0000"
        assert len(data["chart_colors"]) == 2

    @pytest.mark.asyncio
    async def test_returns_error_for_missing(self):
        db = MagicMock()
        db.get_color_scheme = AsyncMock(return_value=None)
        tool = _make_get_color_scheme(db)
        result = await tool.ainvoke({"scheme_id": 999})
        assert "不存在" in result


# ── save_color_scheme tool ────────────────────────────────────────────────────


class TestSaveColorScheme:
    @pytest.mark.asyncio
    async def test_rejects_invalid_density(self):
        db = MagicMock()
        tool = _make_save_color_scheme(db)
        result = await tool.ainvoke({
            "name": "test",
            "label": "测试",
            "colors": {"primary": "ff0000", "accent": "00ff00", "text": "000000",
                        "text_secondary": "666666", "bg": "ffffff",
                        "bg_dark": "eeeeee", "border": "cccccc"},
            "chart_colors": ["ff0000", "00ff00", "0000ff", "ffff00"],
            "fonts": {"title": {}, "subtitle": {}, "body": {}, "caption": {}},
            "style_density": "unknown",
        })
        assert "必须为" in result

    @pytest.mark.asyncio
    async def test_creates_scheme_with_valid_data(self):
        cs = MagicMock()
        cs.id = 42
        cs.name = "valid"
        cs.label = "有效方案"

        db = MagicMock()
        db.create_color_scheme = AsyncMock(return_value=cs)
        tool = _make_save_color_scheme(db)
        result = await tool.ainvoke({
            "name": "valid",
            "label": "有效方案",
            "colors": {"primary": "ff0000", "accent": "00ff00", "text": "000000",
                        "text_secondary": "666666", "bg": "ffffff",
                        "bg_dark": "eeeeee", "border": "cccccc"},
            "chart_colors": ["ff0000", "00ff00", "0000ff", "ffff00"],
            "fonts": {"title": {}, "subtitle": {}, "body": {}, "caption": {}},
            "style_density": "elaborate",
            "decoration": {"corner_bracket": True},
        })
        assert "创建成功" in result
        assert "42" in result


# ── list_layouts tool ─────────────────────────────────────────────────────────


class TestListLayouts:
    @pytest.mark.asyncio
    async def test_returns_all_seven_layouts(self):
        tool = _make_list_layouts()
        result = await tool.ainvoke({"dummy": ""})
        for name in ("title_slide", "section", "content_bullet",
                      "content_two_column", "content_three_column",
                      "content_grid_2x2", "ending"):
            assert name in result, f"Missing {name}"


# ── get_layout tool ───────────────────────────────────────────────────────────


class TestGetLayout:
    @pytest.mark.asyncio
    async def test_returns_valid_json(self):
        tool = _make_get_layout()
        result = await tool.ainvoke({"name": "title_slide"})
        data = json.loads(result)
        assert data["name"] == "title_slide"
        assert "fixed_elements" in data

    @pytest.mark.asyncio
    async def test_unknown_layout_returns_error(self):
        tool = _make_get_layout()
        result = await tool.ainvoke({"name": "nonexistent"})
        assert "不存在" in result
        assert "title_slide" in result  # suggests available


# ── set_presentation_style tool ───────────────────────────────────────────────


class TestSetPresentationStyle:
    @pytest.mark.asyncio
    async def test_sets_and_returns_id(self):
        db = MagicMock()
        db.update_presentation_status = AsyncMock()
        tool, get_result = _make_set_presentation_style(db, presentation_id=10)

        result = await tool.ainvoke({
            "color_scheme_id": 3,
            "design_rationale": "科技主题选蓝色系",
        })
        data = json.loads(result)
        assert data["presentation_id"] == 10
        assert data["color_scheme_id"] == 3
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_result_returns_captured_values(self):
        db = MagicMock()
        db.update_presentation_status = AsyncMock()
        tool, get_result = _make_set_presentation_style(db, presentation_id=10)

        cs_id, rationale, was_called = get_result()
        assert cs_id is None
        assert was_called is False

        await tool.ainvoke({
            "color_scheme_id": 5,
            "design_rationale": "学术暖色",
        })

        cs_id, rationale, was_called = get_result()
        assert cs_id == 5
        assert rationale == "学术暖色"
        assert was_called is True

    @pytest.mark.asyncio
    async def test_updates_presentation_status(self):
        db = MagicMock()
        db.update_presentation_status = AsyncMock()
        tool, _ = _make_set_presentation_style(db, presentation_id=10)

        await tool.ainvoke({
            "color_scheme_id": 1,
            "design_rationale": "test",
        })

        db.update_presentation_status.assert_called_once_with(10, "slides_generating")
