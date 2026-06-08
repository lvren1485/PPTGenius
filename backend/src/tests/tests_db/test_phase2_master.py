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
                {"section_index": 1, "title": "引言", "description": "背景", "slide_number": 3},
                {"section_index": 2, "title": "方法", "description": "技术", "slide_number": 4},
            ],
        })
        assert "已创建大纲" in result
        conv2 = await d.get_conversation(conv.id)
        assert conv2.current_outline_id is not None
        outline = await d.get_outline(conv2.current_outline_id)
        slides = await d.get_slides_by_outline_id(outline.id)
        assert any(s.layout_type == "title" for s in slides)
        assert any(s.layout_type == "thanks" for s in slides)
        # Section slides should be pre-created (section + content per section)
        assert any(s.layout_type == "section" for s in slides)
        assert any(s.layout_type == "content" for s in slides)
        # Each section should have slides assigned
        sections = await d.get_sections_by_outline_id(outline.id)
        assert len(sections) == 2
        for sec in sections:
            sec_slides = [s for s in slides if s.section_id == sec.id]
            assert len(sec_slides) >= 2
        # Verify slide_number is respected: 3 + 4 = 7 body slides
        body = [s for s in slides if s.layout_type in ("section", "content") and s.section_id]
        assert len(body) == 7

    @pytest.mark.asyncio
    async def test_modify_rename(self, db):
        d = Database(db)
        u = await d.create_user("mo2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Modify Test")
        sl = await d.create_outline_slide(o.id, 1, "Old Name")
        await d.set_conversation_outline(conv.id, o.id)
        tool = make_modify_outline_structure(d, conv.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke({"operations": [{"op": "rename", "slide_id": sl.id, "new_title": "New Name"}]})
        assert "rename×1" in r["summary"]
        assert (await d.get_outline_slide(sl.id)).title == "New Name"

    @pytest.mark.asyncio
    async def test_modify_delete_simple(self, db):
        d = Database(db)
        u = await d.create_user("md2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        await d.create_outline_slide(o.id, 1, "Keep")
        s2 = await d.create_outline_slide(o.id, 2, "Delete Me")
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "delete", "target_id": s2.id}]})
        assert len(await d.get_slides_by_outline_id(o.id)) == 1

    @pytest.mark.asyncio
    async def test_modify_delete_with_merge(self, db):
        d = Database(db)
        u = await d.create_user("dm2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Merge Test")
        s1 = await d.create_outline_slide(o.id, 1, "A", content_json={"main_points": ["A1"]})
        s2 = await d.create_outline_slide(o.id, 2, "B", content_json={"main_points": ["B1"]})
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "delete", "target_id": s2.id, "merge_id": s1.id}]})
        assert "占位" in r["summary"]
        s1f = await d.get_outline_slide(s1.id)
        assert "B1" in str(s1f.content_json)
        assert "待合并" in (s1f.title or "")

    @pytest.mark.asyncio
    async def test_modify_insert_simple(self, db):
        d = Database(db)
        u = await d.create_user("mi2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        s1 = await d.create_outline_slide(o.id, 1, "First")
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "insert", "after_id": s1.id}]})
        assert len(await d.get_slides_by_outline_id(o.id)) == 2

    @pytest.mark.asyncio
    async def test_modify_insert_split(self, db):
        d = Database(db)
        u = await d.create_user("ms2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        s1 = await d.create_outline_slide(o.id, 1, "Original")
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "insert", "after_id": s1.id, "is_copy": True}]})
        s1f = await d.get_outline_slide(s1.id)
        assert "待分割" in (s1f.title or "")
        slides = await d.get_slides_by_outline_id(o.id)
        assert len(slides) == 2

    @pytest.mark.asyncio
    async def test_modify_move(self, db):
        d = Database(db)
        u = await d.create_user("mm2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        sec = await d.create_outline_section(o.id, 1, "S1")
        s1 = await d.create_outline_slide(o.id, 1, "A", section_id=sec.id)
        s2 = await d.create_outline_slide(o.id, 2, "B", section_id=sec.id)
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "move", "target_id": s1.id, "after_id": s2.id}]})
        slides = await d.get_slides_by_outline_id(o.id)
        assert slides[-1].id == s1.id

    @pytest.mark.asyncio
    async def test_modify_move_cross_section_rejected(self, db):
        d = Database(db)
        u = await d.create_user("mx2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        sec1 = await d.create_outline_section(o.id, 1, "S1")
        sec2 = await d.create_outline_section(o.id, 2, "S2")
        s1 = await d.create_outline_slide(o.id, 1, "A", section_id=sec1.id)
        s2 = await d.create_outline_slide(o.id, 2, "B", section_id=sec2.id)
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "move", "target_id": s1.id, "after_id": s2.id}]})
        assert "is_change_section=true" in r.get("summary", "")

    @pytest.mark.asyncio
    async def test_modify_duplicate_ids_rejected(self, db):
        d = Database(db)
        u = await d.create_user("dup_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        s1 = await d.create_outline_slide(o.id, 1, "X")
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke({"operations": [
            {"op": "rename", "slide_id": s1.id, "new_title": "A"},
            {"op": "rename", "slide_id": s1.id, "new_title": "B"},
        ]})
        assert "重复" in r["error"]

    @pytest.mark.asyncio
    async def test_modify_no_outline_error(self, db):
        d = Database(db)
        u = await d.create_user("moe2_user")
        conv = await d.create_conversation(u.id)
        tool = make_modify_outline_structure(d, conv.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke({"operations": [{"op": "rename", "slide_id": 99999, "new_title": "X"}]})
        assert "error" in r


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
