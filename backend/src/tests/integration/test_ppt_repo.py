"""Tests for Phase 0 PPT repository changes — style_id, removed retry, set_slide_agent_output."""

import pytest_asyncio

from pptgenius.infrastructure.db.database import Database


class TestPresentationWithStyleId:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("pres_user")
        conv = await Database(db).create_conversation(u.id)
        return Database(db), u, conv

    async def test_create_presentation_with_style(self, d):
        db_obj, user, conv = d
        s = await db_obj.create_style(
            name="pres_style", label="PS",
            colors_json={}, chart_colors_json=[], fonts_json={},
        )
        pres = await db_obj.create_presentation(
            user.id, conv.id, style_id=s.id,
        )
        assert pres.style_id == s.id
        assert pres.status == "pending"

    async def test_create_presentation_no_style(self, d):
        db_obj, user, conv = d
        pres = await db_obj.create_presentation(user.id, conv.id)
        assert pres.style_id is None

    async def test_set_presentation_style(self, d):
        db_obj, user, conv = d
        s1 = await db_obj.create_style(
            name="s1", label="S1",
            colors_json={}, chart_colors_json=[], fonts_json={},
        )
        s2 = await db_obj.create_style(
            name="s2", label="S2",
            colors_json={}, chart_colors_json=[], fonts_json={},
        )
        pres = await db_obj.create_presentation(user.id, conv.id, style_id=s1.id)
        await db_obj.set_presentation_style(pres.id, s2.id)
        fetched = await db_obj.get_presentation(pres.id)
        assert fetched.style_id == s2.id

    async def test_get_presentation(self, d):
        db_obj, user, conv = d
        pres = await db_obj.create_presentation(user.id, conv.id)
        fetched = await db_obj.get_presentation(pres.id)
        assert fetched is not None

class TestPresentationSlideWithStyleId:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("pslide_user")
        conv = await Database(db).create_conversation(u.id)
        pres = await Database(db).create_presentation(u.id, conv.id)
        return Database(db), pres

    async def test_create_slide_with_style(self, d):
        db_obj, pres = d
        slide = await db_obj.create_presentation_slide(
            pres.id, slide_index=0, layout_name="title_slide", style_id=None,
        )
        assert slide.style_id is None
        assert slide.layout_name == "title_slide"

    async def test_batch_create_slides(self, d):
        db_obj, pres = d
        slides = await db_obj.create_presentation_slides_batch([
            {"presentation_id": pres.id, "slide_index": 0, "layout_name": "title_slide"},
            {"presentation_id": pres.id, "slide_index": 1, "layout_name": "content_bullet"},
            {"presentation_id": pres.id, "slide_index": 2, "layout_name": "ending"},
        ])
        assert len(slides) == 3

    async def test_set_slide_agent_output(self, d):
        db_obj, pres = d
        s = await db_obj.create_presentation_slide(pres.id, 0, "content")
        outputs = {"elements": [{"type": "textbox"}], "notes": "hello", "background": {}}
        await db_obj.set_slide_agent_output(pres.id, 0, outputs)
        fetched = await db_obj.get_presentation_slide(s.id)
        assert fetched.agent_outputs == outputs

    async def test_update_slides_style(self, d):
        db_obj, pres = d
        style = await db_obj.create_style(
            name="batch_style", label="BS",
            colors_json={}, chart_colors_json=[], fonts_json={},
        )
        await db_obj.create_presentation_slide(pres.id, 0, "title_slide")
        await db_obj.create_presentation_slide(pres.id, 1, "content_bullet")
        count = await db_obj.update_slides_style(pres.id, style.id)
        assert count == 2

    async def test_update_slide_status(self, d):
        db_obj, pres = d
        await db_obj.create_presentation_slide(pres.id, 0, "content")
        assert await db_obj.update_slide_status(pres.id, 0, "completed")
        fetched = (await db_obj.get_slides_by_presentation_id(pres.id))[0]
        assert fetched.status == "completed"

    async def test_slide_status_with_error(self, d):
        db_obj, pres = d
        await db_obj.create_presentation_slide(pres.id, 0, "content")
        await db_obj.update_slide_status(pres.id, 0, "failed")
        fetched = (await db_obj.get_slides_by_presentation_id(pres.id))[0]
        assert fetched.status == "failed"

    async def test_no_retry_methods(self, d):
        """increment_slide_retry* should not exist."""
        assert not hasattr(Database, "increment_slide_retry")
        assert not hasattr(Database, "increment_slide_retry_by_index")

    async def test_replace_presentation_slides(self, d):
        db_obj, pres = d
        await db_obj.create_presentation_slide(pres.id, 0, "old_layout")
        new_slides = await db_obj.replace_presentation_slides(pres.id, [
            {"slide_index": 1, "layout_name": "new_layout"},
            {"slide_index": 2, "layout_name": "ending"},
        ])
        assert len(new_slides) == 2
        all_slides = await db_obj.get_slides_by_presentation_id(pres.id)
        assert len(all_slides) == 2
        assert all_slides[0].slide_index == 1


