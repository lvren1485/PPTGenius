"""Tests for new Style repository (replaces ColorScheme + Template)."""

import pytest_asyncio

from pptgenius.infrastructure.db.database import Database


class TestStyleRepo:
    @pytest_asyncio.fixture
    async def d(self, db):
        return Database(db)

    async def test_create_style(self, d):
        s = await d.create_style(
            name="test_style",
            label="Test Style",
            colors_json={"primary": "ff0000"},
            chart_colors_json=["ff0000", "00ff00"],
            fonts_json={"body": {"name": "Arial", "size": 14}},
            style_density="moderate",
            decoration_json={"title_accent_bar": True},
            background_json={"color": "ffffff"},
        )
        assert s.id is not None
        assert s.name == "test_style"
        assert s.label == "Test Style"
        assert s.background_json == {"color": "ffffff"}

    async def test_search_styles_by_name(self, d):
        await d.create_style(
            name="corp_blue", label="Corporate Blue",
            colors_json={}, chart_colors_json=[], fonts_json={},
        )
        await d.create_style(
            name="tech_green", label="Tech Green",
            colors_json={}, chart_colors_json=[], fonts_json={},
        )
        styles = await d.search_styles("corp")
        assert len(styles) >= 1
        assert any(s.name == "corp_blue" for s in styles)

    async def test_search_styles_by_label(self, d):
        await d.create_style(
            name="minimal_white", label="Minimal White",
            colors_json={}, chart_colors_json=[], fonts_json={},
        )
        styles = await d.search_styles("minimal")
        assert len(styles) >= 1
        assert any(s.label == "Minimal White" for s in styles)

    async def test_search_styles_no_match(self, d):
        styles = await d.search_styles("zzz_nonexistent")
        assert len(styles) == 0

    async def test_get_style(self, d):
        s = await d.create_style(
            name="get_test", label="Get",
            colors_json={}, chart_colors_json=[], fonts_json={},
        )
        fetched = await d.get_style(s.id)
        assert fetched is not None
        assert fetched.name == "get_test"

    async def test_get_style_nonexistent(self, d):
        assert await d.get_style(99999) is None
