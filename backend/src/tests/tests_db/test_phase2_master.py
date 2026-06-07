"""Tests for Phase 2 — Master Agent tools (perception + structure)."""

import pytest

from pptgenius.infrastructure.db.database import Database


class TestPerceptionTools:
    @pytest.mark.asyncio
    async def test_get_conversation_status(self, db):
        d = Database(db)
        u = await d.create_user("per_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test Outline")
        await d.set_conversation_outline(conv.id, o.id)
        tool = make_get_conversation_status(d, conv.id)
        result = await tool.ainvoke({})
        assert result["conversation_id"] == conv.id
        assert result["current_outline_id"] == o.id
        assert len(result["outlines"]) >= 1

    @pytest.mark.asyncio
    async def test_switch_outline(self, db):
        d = Database(db)
        u = await d.create_user("sw_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Switch Target")
        tool = make_switch_outline(d, conv.id)
        result = await tool.ainvoke({"outline_id": o.id})
        assert f"已切换到大纲" in result
        conv2 = await d.get_conversation(conv.id)
        assert conv2.current_outline_id == o.id

    @pytest.mark.asyncio
    async def test_switch_outline_null(self, db):
        d = Database(db)
        u = await d.create_user("sw2_user")
        conv = await d.create_conversation(u.id)
        tool = make_switch_outline(d, conv.id)
        result = await tool.ainvoke({"outline_id": None})
        assert "已取消选中大纲" in result

    @pytest.mark.asyncio
    async def test_get_outline(self, db):
        d = Database(db)
        u = await d.create_user("go_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Get Outline")
        sec = await d.create_outline_section(o.id, 1, "Sec 1")
        await d.create_outline_slide(o.id, 1, "Slide 1", section_id=sec.id)
        await d.set_conversation_outline(conv.id, o.id)
        tool = make_get_outline(d, conv.id)
        result = await tool.ainvoke({})
        assert result["title"] == "Get Outline"
        assert len(result["sections"]) == 1

    @pytest.mark.asyncio
    async def test_get_outline_no_selection(self, db):
        d = Database(db)
        u = await d.create_user("go2_user")
        conv = await d.create_conversation(u.id)
        tool = make_get_outline(d, conv.id)
        result = await tool.ainvoke({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_outline_slide(self, db):
        d = Database(db)
        u = await d.create_user("gos_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Slide Detail")
        sl = await d.create_outline_slide(o.id, 1, "Detail Slide",
                                           content_json={"main_points": ["A", "B"]})
        tool = make_get_outline_slide(d, conv.id)
        result = await tool.ainvoke({"slide_id": sl.id})
        assert result["title"] == "Detail Slide"
        assert result["content_json"]["main_points"] == ["A", "B"]

    @pytest.mark.asyncio
    async def test_list_styles(self, db):
        d = Database(db)
        u = await d.create_user("ls_user")
        conv = await d.create_conversation(u.id)
        await d.create_style(name="test_blue", label="Test Blue",
                             colors_json={}, chart_colors_json=[], fonts_json={})
        tool = make_list_styles(d, conv.id)
        result = await tool.ainvoke({"query": "blue"})
        assert len(result) >= 1
        assert any(s["name"] == "test_blue" for s in result)


class TestStructureTools:
    @pytest.mark.asyncio
    async def test_write_outline_structure(self, db):
        d = Database(db)
        u = await d.create_user("ws_user")
        conv = await d.create_conversation(u.id)
        tool = make_write_outline_structure(d, conv.id)
        result = await tool.ainvoke({
            "title": "AI报告",
            "sections": [
                {"section_index": 1, "title": "引言", "description": "背景"},
                {"section_index": 2, "title": "方法", "description": "技术"},
            ],
        })
        assert "已创建大纲" in result
        conv2 = await d.get_conversation(conv.id)
        assert conv2.current_outline_id is not None
        # title_slide and ending_slide should be auto-created
        outline = await d.get_outline(conv2.current_outline_id)
        slides = await d.get_slides_by_outline_id(outline.id)
        assert any(s.layout_type == "title" for s in slides)
        assert any(s.layout_type == "thanks" for s in slides)
        sections = await d.get_sections_by_outline_id(outline.id)
        assert len(sections) == 2

    @pytest.mark.asyncio
    async def test_modify_outline_structure_rename(self, db):
        d = Database(db)
        u = await d.create_user("mo_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Modify Test")
        sl = await d.create_outline_slide(o.id, 1, "Old Name")
        await d.set_conversation_outline(conv.id, o.id)
        tool = make_modify_outline_structure(d, conv.id)
        result = await tool.ainvoke({
            "operations": [{"op": "rename_slide", "slide_index": 1, "new_title": "New Name"}],
        })
        assert "rename×1" in result
        fetched = await d.get_outline_slide(sl.id)
        assert fetched.title == "New Name"

    @pytest.mark.asyncio
    async def test_modify_outline_structure_delete(self, db):
        d = Database(db)
        u = await d.create_user("md_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Delete Test")
        await d.create_outline_slide(o.id, 1, "Keep")
        await d.create_outline_slide(o.id, 2, "Delete Me")
        await d.set_conversation_outline(conv.id, o.id)
        tool = make_modify_outline_structure(d, conv.id)
        result = await tool.ainvoke({
            "operations": [{"op": "delete_slide", "slide_index": 2}],
        })
        assert "delete×1" in result
        slides = await d.get_slides_by_outline_id(o.id)
        assert len(slides) == 1

    @pytest.mark.asyncio
    async def test_modify_outline_structure_insert(self, db):
        d = Database(db)
        u = await d.create_user("mi_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Insert Test")
        await d.create_outline_slide(o.id, 1, "First")
        await d.create_outline_slide(o.id, 2, "Third")
        await d.set_conversation_outline(conv.id, o.id)
        tool = make_modify_outline_structure(d, conv.id)
        result = await tool.ainvoke({
            "operations": [{"op": "insert_slide", "after_slide_index": 1, "title": "Second"}],
        })
        assert "占位×1" in result
        slides = await d.get_slides_by_outline_id(o.id)
        assert len(slides) == 3

    @pytest.mark.asyncio
    async def test_modify_outline_no_outline_error(self, db):
        d = Database(db)
        u = await d.create_user("moe_user")
        conv = await d.create_conversation(u.id)
        tool = make_modify_outline_structure(d, conv.id)
        result = await tool.ainvoke({"operations": [{"op": "rename_slide", "slide_index": 1, "new_title": "X"}]})
        assert "错误" in result or "error" in result.lower()


# Import tool factories at module level for test discovery
from pptgenius.agent.tools.perception import (
    make_get_conversation_status,
    make_get_knowledge_files,
    make_get_outline,
    make_get_outline_slide,
    make_get_presentation,
    make_list_styles,
    make_switch_outline,
)
from pptgenius.agent.tools.structure import make_modify_outline_structure, make_write_outline_structure
