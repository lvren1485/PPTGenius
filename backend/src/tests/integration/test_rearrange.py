"""Tests for §4 rearrange — modify cascades o_modified_* to pres slides,
and rearrange_presentation_slides reconciles them.
"""

import pytest
import pytest_asyncio

from pptgenius.agent.tools.structure import (
    make_modify_outline_structure,
    make_rearrange_presentation_slides,
    make_write_outline_structure,
)
from pptgenius.infrastructure.db.database import Database


class TestModifyCascadeToPresSlides:
    """modify_outline_structure sets o_modified_* on matching pres slides."""

    @pytest_asyncio.fixture
    async def d(self, db):
        d = Database(db)
        u = await d.create_user("cas_user")
        conv = await d.create_conversation(u.id)
        # Create outline with 3 slides
        o = await d.create_outline(u.id, conv.id, "Cascade Test")
        s1 = await d.create_outline_slide(o.id, 1, "Slide A")
        s2 = await d.create_outline_slide(o.id, 2, "Slide B")
        s3 = await d.create_outline_slide(o.id, 3, "Slide C")
        await d.set_conversation_outline(conv.id, o.id)
        # Create presentation with matching pres slides
        pres = await d.create_presentation(u.id, conv.id, outline_id=o.id)
        for sid in (s1.id, s2.id, s3.id):
            await d.create_presentation_slide(pres.id, 0, "content", outline_slide_id=sid)
        return d, conv, o, pres, s1, s2, s3

    async def _find_pres_slides(self, d, pres_id):
        return await d.get_slides_by_presentation_id(pres_id)

    async def _pres_by_outline(self, d, pres_id, outline_slide_id):
        all_ps = await self._find_pres_slides(d, pres_id)
        for ps in all_ps:
            if ps.outline_slide_id == outline_slide_id:
                return ps
        return None

    # ── rename ───────────────────────────────────────────────────────────

    async def test_rename_with_modify_cascades_to_pres(self, d):
        d_obj, conv, o, pres, s1, s2, s3 = d
        r = await make_modify_outline_structure(d_obj, conv.id).ainvoke(
            {"operations": [{"op": "rename", "slide_id": s1.id,
                             "new_title": "Changed", "modify_content": True}]})
        ps = await self._pres_by_outline(d_obj, pres.id, s1.id)
        assert ps.status == "o_modified_modify"

    async def test_rename_without_modify_no_cascade(self, d):
        d_obj, conv, o, pres, s1, s2, s3 = d
        await make_modify_outline_structure(d_obj, conv.id).ainvoke(
            {"operations": [{"op": "rename", "slide_id": s1.id,
                             "new_title": "Just Rename"}]})
        ps = await self._pres_by_outline(d_obj, pres.id, s1.id)
        assert ps.status in ("new", None)

    # ── delete ───────────────────────────────────────────────────────────

    async def test_delete_with_merge_cascades_to_pres(self, d):
        d_obj, conv, o, pres, s1, s2, s3 = d
        # Delete s1, merge content into s2
        await make_modify_outline_structure(d_obj, conv.id).ainvoke(
            {"operations": [{"op": "delete", "target_id": s1.id, "merge_id": s2.id}]})
        # s2 (merge target) should cascade
        ps2 = await self._pres_by_outline(d_obj, pres.id, s2.id)
        assert ps2.status == "o_modified_merge"
        # s1 deleted → pres cascade "o_modified_deleted"
        ps1 = await self._pres_by_outline(d_obj, pres.id, s1.id)
        assert ps1.status == "o_modified_deleted"

    async def test_delete_without_merge_cascades_to_pres(self, d):
        d_obj, conv, o, pres, s1, s2, s3 = d
        await make_modify_outline_structure(d_obj, conv.id).ainvoke(
            {"operations": [{"op": "delete", "target_id": s3.id}]})
        ps3 = await self._pres_by_outline(d_obj, pres.id, s3.id)
        assert ps3.status == "o_modified_deleted"

    # ── insert ───────────────────────────────────────────────────────────

    async def test_insert_new_slide_pres_created_by_rearrange(self, d):
        d_obj, conv, o, pres, s1, s2, s3 = d
        await make_modify_outline_structure(d_obj, conv.id).ainvoke(
            {"operations": [{"op": "insert", "after_id": s1.id, "is_copy": False}]})
        # New outline slide created; pres slide may not exist yet.
        # rearrange should create it.
        await make_rearrange_presentation_slides(d_obj, conv.id).ainvoke({})
        all_ps = await self._find_pres_slides(d_obj, pres.id)
        assert len(all_ps) >= 1  # at least some exist

    async def test_insert_split_cascades_to_pres(self, d):
        d_obj, conv, o, pres, s1, s2, s3 = d
        await make_modify_outline_structure(d_obj, conv.id).ainvoke(
            {"operations": [{"op": "insert", "after_id": s1.id, "is_copy": True}]})
        ps1 = await self._pres_by_outline(d_obj, pres.id, s1.id)
        assert ps1.status == "o_modified_split"


class TestRearrangePresentationSlides:
    """rearrange_presentation_slides handles o_modified_* statuses."""

    @pytest_asyncio.fixture
    async def d_setup(self, db):
        d = Database(db)
        u = await d.create_user("arr_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Rearrange Test")
        s1 = await d.create_outline_slide(o.id, 1, "P1")
        s2 = await d.create_outline_slide(o.id, 2, "P2")
        s3 = await d.create_outline_slide(o.id, 3, "P3")
        await d.set_conversation_outline(conv.id, o.id)
        pres = await d.create_presentation(u.id, conv.id, outline_id=o.id)
        ps1 = await d.create_presentation_slide(pres.id, 1, "content", outline_slide_id=s1.id)
        ps2 = await d.create_presentation_slide(pres.id, 2, "content", outline_slide_id=s2.id)
        ps3 = await d.create_presentation_slide(pres.id, 3, "content", outline_slide_id=s3.id)
        return d, conv, o, pres, [s1, s2, s3], [ps1, ps2, ps3]

    async def _pres_slides(self, d, pres_id):
        return await d.get_slides_by_presentation_id(pres_id)

    async def test_rearrange_soft_deletes_o_modified_deleted(self, d_setup):
        d, conv, o, pres, oslides, pslides = d_setup
        # Use modify_outline_structure to properly delete outline slide + cascade
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "delete", "target_id": oslides[1].id}]})
        assert "占位" not in r["summary"]  # no merge = no placeholder
        await make_rearrange_presentation_slides(d, conv.id).ainvoke({})
        remaining = await self._pres_slides(d, pres.id)
        assert len(remaining) == 2

    async def test_rearrange_keeps_modified_status(self, d_setup):
        d, conv, o, pres, oslides, pslides = d_setup
        from pptgenius.infrastructure.db.models import PresentationSlide
        from sqlalchemy import update
        await d.db.execute(
            update(PresentationSlide)
            .where(PresentationSlide.id == pslides[0].id)
            .values(status="o_modified_modify")
        )
        await d.db.commit()
        await make_rearrange_presentation_slides(d, conv.id).ainvoke({})
        all_ps = await self._pres_slides(d, pres.id)
        ps0 = next(ps for ps in all_ps if ps.id == pslides[0].id)
        assert ps0.status == "o_modified_modify"  # kept for content agent

    async def test_rearrange_reindexes_to_match_outline(self, d_setup):
        d, conv, o, pres, oslides, pslides = d_setup
        # Swap slide_index 1↔2 on outline sides
        from pptgenius.infrastructure.db.models import OutlineSlide
        from sqlalchemy import update
        await d.db.execute(
            update(OutlineSlide)
            .where(OutlineSlide.id == oslides[0].id)
            .values(slide_index=2)
        )
        await d.db.execute(
            update(OutlineSlide)
            .where(OutlineSlide.id == oslides[1].id)
            .values(slide_index=1)
        )
        await d.db.commit()
        await make_rearrange_presentation_slides(d, conv.id).ainvoke({})
        all_ps = await self._pres_slides(d, pres.id)
        for ps in all_ps:
            for o_slide in oslides:
                if ps.outline_slide_id == o_slide.id:
                    assert ps.slide_index == o_slide.slide_index

    async def test_rearrange_noop_when_clean(self, d_setup):
        d, conv, o, pres, oslides, pslides = d_setup
        r = await make_rearrange_presentation_slides(d, conv.id).ainvoke({})
        assert "删除 0" in r
        assert "新建 0" in r
        all_ps = await self._pres_slides(d, pres.id)
        assert len(all_ps) == 3


class TestOutlineSoftDeleteFilter:
    """get_slides_by_outline_id / get_outline_slide filter out status='deleted'."""

    @pytest_asyncio.fixture
    async def d(self, db):
        d = Database(db)
        u = await d.create_user("sf_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "SoftDelTest")
        s1 = await d.create_outline_slide(o.id, 1, "Keep")
        s2 = await d.create_outline_slide(o.id, 2, "Del")
        await d.update_outline_slide_status(s2.id, "deleted")
        return d, o, s1, s2

    async def test_get_slides_filters_deleted(self, d):
        d_obj, o, s1, s2 = d
        slides = await d_obj.get_slides_by_outline_id(o.id)
        assert len(slides) == 1
        assert slides[0].id == s1.id

    async def test_get_slide_returns_none_for_deleted(self, d):
        d_obj, o, s1, s2 = d
        assert await d_obj.get_outline_slide(s2.id) is None

    async def test_get_slide_returns_live(self, d):
        d_obj, o, s1, s2 = d
        fetched = await d_obj.get_outline_slide(s1.id)
        assert fetched is not None
        assert fetched.title == "Keep"

    async def test_soft_delete_outline_slide(self, d):
        d_obj, o, s1, s2 = d
        assert await d_obj.soft_delete_outline_slide(s1.id)
        assert await d_obj.get_outline_slide(s1.id) is None

    async def test_soft_delete_nonexistent(self, d):
        d_obj, o, s1, s2 = d
        assert await d_obj.soft_delete_outline_slide(99999) is False


class TestPresSlideSoftDeleteFilter:
    """get_slides_by_presentation_id / get_presentation_slide filter status='deleted'."""

    @pytest_asyncio.fixture
    async def d(self, db):
        d = Database(db)
        u = await d.create_user("psf_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "PSF Test")
        s1 = await d.create_outline_slide(o.id, 1, "A")
        s2 = await d.create_outline_slide(o.id, 2, "B")
        await d.set_conversation_outline(conv.id, o.id)
        pres = await d.create_presentation(u.id, conv.id, outline_id=o.id)
        ps1 = await d.create_presentation_slide(pres.id, 1, "content", outline_slide_id=s1.id)
        ps2 = await d.create_presentation_slide(pres.id, 2, "content", outline_slide_id=s2.id)
        return d, pres, ps1, ps2

    async def test_get_pres_slides_filters_deleted(self, d):
        d_obj, pres, ps1, ps2 = d
        await d_obj.soft_delete_presentation_slide(ps2.id)
        slides = await d_obj.get_slides_by_presentation_id(pres.id)
        assert len(slides) == 1
        assert slides[0].id == ps1.id

    async def test_get_pres_slide_returns_none_for_deleted(self, d):
        d_obj, pres, ps1, ps2 = d
        await d_obj.soft_delete_presentation_slide(ps2.id)
        assert await d_obj.get_presentation_slide(ps2.id) is None

    async def test_get_pres_slide_returns_live(self, d):
        d_obj, pres, ps1, ps2 = d
        fetched = await d_obj.get_presentation_slide(ps1.id)
        assert fetched is not None


class TestFullModifyRearrangeCycle:
    """End-to-end: modify → rearrange → verify pres slides match outline."""

    @pytest_asyncio.fixture
    async def d(self, db):
        d = Database(db)
        u = await d.create_user("e2e_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "E2E Test")
        for i, title in enumerate(["Intro", "Body A", "Body B", "Conclusion"], start=1):
            await d.create_outline_slide(o.id, i, title)
        await d.set_conversation_outline(conv.id, o.id)
        pres = await d.create_presentation(u.id, conv.id, outline_id=o.id)
        for i in range(1, 5):
            await d.create_presentation_slide(
                pres.id, i, "content",
                outline_slide_id=(await d.get_slides_by_outline_id(o.id))[i - 1].id,
            )
        return d, conv, o, pres

    async def test_delete_then_rearrange(self, d):
        d_obj, conv, o, pres = d
        oslides = await d_obj.get_slides_by_outline_id(o.id)
        # Delete slide 2 (Body A) with merge to slide 3 (Body B)
        r = await make_modify_outline_structure(d_obj, conv.id).ainvoke(
            {"operations": [{"op": "delete", "target_id": oslides[1].id,
                             "merge_id": oslides[2].id}]})
        assert "占位" in r["summary"]
        # Rearrange
        await make_rearrange_presentation_slides(d_obj, conv.id).ainvoke({})
        # Verify: 3 outline slides, 3 pres slides
        oslides_after = await d_obj.get_slides_by_outline_id(o.id)
        pres_after = await d_obj.get_slides_by_presentation_id(pres.id)
        assert len(oslides_after) == len(pres_after)
        # Pres slide index should match outline slide_index
        for oslide in oslides_after:
            for ps in pres_after:
                if ps.outline_slide_id == oslide.id:
                    assert ps.slide_index == oslide.slide_index

    async def test_insert_then_rearrange(self, d):
        d_obj, conv, o, pres = d
        oslides = await d_obj.get_slides_by_outline_id(o.id)
        r = await make_modify_outline_structure(d_obj, conv.id).ainvoke(
            {"operations": [{"op": "insert", "after_id": oslides[0].id, "is_copy": False}]})
        assert "占位" in r["summary"]
        await make_rearrange_presentation_slides(d_obj, conv.id).ainvoke({})
        oslides_after = await d_obj.get_slides_by_outline_id(o.id)
        pres_after = await d_obj.get_slides_by_presentation_id(pres.id)
        assert len(oslides_after) == len(pres_after)

    async def test_multiple_ops_then_rearrange(self, d):
        d_obj, conv, o, pres = d
        oslides = await d_obj.get_slides_by_outline_id(o.id)
        r = await make_modify_outline_structure(d_obj, conv.id).ainvoke(
            {"operations": [
                {"op": "rename", "slide_id": oslides[0].id, "new_title": "New Intro",
                 "modify_content": True},
                {"op": "rename", "slide_id": oslides[1].id, "new_title": "Renamed Body",
                 "modify_content": False},
                {"op": "insert", "after_id": oslides[2].id, "is_copy": False},
            ]})
        assert "占位" in r["summary"]
        await make_rearrange_presentation_slides(d_obj, conv.id).ainvoke({})
        oslides_after = await d_obj.get_slides_by_outline_id(o.id)
        pres_after = await d_obj.get_slides_by_presentation_id(pres.id)
        assert len(oslides_after) == len(pres_after)
        # All pres slides should have matching outline IDs
        oslide_ids = {s.id for s in oslides_after}
        for ps in pres_after:
            assert ps.outline_slide_id in oslide_ids
