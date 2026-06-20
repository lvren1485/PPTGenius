"""Tests for Phase 0 outline repository changes — sections, slides with section_id, eval_detail."""

import pytest_asyncio

from pptgenius.infrastructure.db.database import Database


class TestOutlineSectionRepo:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("osec_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, "Sections Test")
        return Database(db), o

    async def test_create_section(self, d):
        db_obj, outline = d
        s = await db_obj.create_outline_section(
            outline.id, section_index=1, title="Introduction",
            description="Background and context",
        )
        assert s.id is not None
        assert s.section_index == 1
        assert s.title == "Introduction"
        assert s.description == "Background and context"

    async def test_get_section(self, d):
        db_obj, outline = d
        s = await db_obj.create_outline_section(outline.id, 1, "Methods")
        fetched = await db_obj.get_outline_section(s.id)
        assert fetched.title == "Methods"

    async def test_get_sections_by_outline_id(self, d):
        db_obj, outline = d
        await db_obj.create_outline_section(outline.id, 2, "Section 2")
        await db_obj.create_outline_section(outline.id, 1, "Section 1")
        await db_obj.create_outline_section(outline.id, 3, "Section 3")
        sections = await db_obj.get_sections_by_outline_id(outline.id)
        assert len(sections) == 3
        assert [s.section_index for s in sections] == [1, 2, 3]

    async def test_update_section(self, d):
        db_obj, outline = d
        s = await db_obj.create_outline_section(outline.id, 1, "Old")
        assert await db_obj.update_outline_section(
            s.id, title="New Title", slide_count=5
        )
        fetched = await db_obj.get_outline_section(s.id)
        assert fetched.title == "New Title"
        assert fetched.slide_count == 5

    async def test_delete_section(self, d):
        db_obj, outline = d
        s = await db_obj.create_outline_section(outline.id, 1, "Temp")
        assert await db_obj.delete_outline_section(s.id)
        assert await db_obj.get_outline_section(s.id) is None

    async def test_get_section_nonexistent(self, d):
        db_obj, _ = d
        assert await db_obj.get_outline_section(99999) is None


class TestOutlineSlideWithSection:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("oslide_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, "Slide Section")
        s = await Database(db).create_outline_section(o.id, 1, "S1")
        return Database(db), o, s

    async def test_create_slide_with_section_id(self, d):
        db_obj, outline, section = d
        slide = await db_obj.create_outline_slide(
            outline.id, slide_index=1, title="Page 1",
            section_id=section.id, layout_type="content",
        )
        assert slide.section_id == section.id
        assert slide.title == "Page 1"
        assert slide.status == "new"

    async def test_slides_belong_to_section(self, d):
        db_obj, outline, section = d
        s1 = await db_obj.create_outline_slide(
            outline.id, 1, "Slide 1", section_id=section.id,
        )
        s2 = await db_obj.create_outline_slide(
            outline.id, 2, "Slide 2", section_id=section.id,
        )
        slides = await db_obj.get_slides_by_outline_id(outline.id)
        assert len(slides) == 2
        assert all(s.section_id == section.id for s in slides)

    async def test_slide_without_section(self, d):
        db_obj, outline, _ = d
        slide = await db_obj.create_outline_slide(
            outline.id, 1, "No Section",
        )
        assert slide.section_id is None


class TestOutlineEvalDetail:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("eval_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, "Eval Test")
        return Database(db), o

    async def test_update_eval_with_detail(self, d):
        db_obj, outline = d
        detail = {"overall": 8.0, "suggestions": ["Add more data", "Reorganize §2"]}
        await db_obj.update_outline_eval(outline.id, 8.0, detail)
        fetched = await db_obj.get_outline(outline.id)
        assert fetched.eval_score == 8.0
        assert fetched.eval_detail == detail

    async def test_update_eval_score_only(self, d):
        db_obj, outline = d
        await db_obj.update_outline_eval(outline.id, 6.5)
        fetched = await db_obj.get_outline(outline.id)
        assert fetched.eval_score == 6.5
        assert fetched.eval_detail is None


class TestOutlineVersion:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("ver_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, "Ver Test")
        return Database(db), o

    async def test_increase_version(self, d):
        db_obj, outline = d
        await db_obj.increase_outline_version(outline.id)
        await db_obj.increase_outline_version(outline.id)
        await db_obj.increase_outline_version(outline.id)
        fetched = await db_obj.get_outline(outline.id)
        assert fetched.version == 3

    async def test_version_defaults(self, d):
        db_obj, outline = d
        assert outline.version == 0

    async def test_version_is_int(self, d):
        db_obj, outline = d
        assert isinstance(outline.version, int)


class TestOutlineSlideCitations:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("cite_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, "Cite Test")
        slide = await Database(db).create_outline_slide(o.id, 1, "C1")
        return Database(db), slide

    async def test_set_citations(self, d):
        db_obj, slide = d
        citations = [{"knowledge_file_id": 1}, {"knowledge_file_id": 2, "web_url": "https://x.com"}]
        await db_obj.update_outline_slide_citations(slide.id, citations)
        fetched = await db_obj.get_outline_slide(slide.id)
        assert fetched.citations == citations

    async def test_update_slide_status(self, d):
        db_obj, slide = d
        await db_obj.update_outline_slide_status(slide.id, "completed")
        fetched = await db_obj.get_outline_slide(slide.id)
        assert fetched.status == "completed"

    async def test_update_slide_with_status(self, d):
        db_obj, slide = d
        await db_obj.update_outline_slide(slide.id, title="New Title", status="done")
        fetched = await db_obj.get_outline_slide(slide.id)
        assert fetched.title == "New Title"
        assert fetched.status == "done"


class TestOutlineSlideIndex:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("idx_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, "Index Test")
        # Create slides at index 1,2,3,4
        for i in range(1, 5):
            await Database(db).create_outline_slide(o.id, i, f"Slide {i}")
        return Database(db), o

    async def test_update_slide_index(self, d):
        db_obj, outline = d
        slides = await db_obj.get_slides_by_outline_id(outline.id)
        s2 = [s for s in slides if s.slide_index == 2][0]
        await db_obj.update_outline_slide_index(s2.id, 10)
        fetched = await db_obj.get_outline_slide(s2.id)
        assert fetched.slide_index == 10

    async def test_update_slide_index_zero_rejected(self, d):
        db_obj, outline = d
        slides = await db_obj.get_slides_by_outline_id(outline.id)
        s1 = [s for s in slides if s.slide_index == 1][0]
        assert await db_obj.update_outline_slide_index(s1.id, 0) is False

    async def test_delete_reindexes_subsequent(self, d):
        db_obj, outline = d
        slides = await db_obj.get_slides_by_outline_id(outline.id)
        s2 = [s for s in slides if s.slide_index == 2][0]
        await db_obj.delete_outline_slide(s2.id)
        # After deletion: index 1,3,4 → should be 1,2,3
        remaining = await db_obj.get_slides_by_outline_id(outline.id)
        assert len(remaining) == 3
        assert [s.slide_index for s in remaining] == [1, 2, 3]

    async def test_insert_after_shifts_subsequent(self, d):
        db_obj, outline = d
        slides = await db_obj.get_slides_by_outline_id(outline.id)
        s2 = [s for s in slides if s.slide_index == 2][0]
        new_slide = await db_obj.insert_outline_slide_after(
            outline.id, after_slide_id=s2.id, title="Inserted",
        )
        assert new_slide.slide_index == 3
        all_slides = await db_obj.get_slides_by_outline_id(outline.id)
        assert len(all_slides) == 5
        assert [s.slide_index for s in all_slides] == [1, 2, 3, 4, 5]
        titles = {s.slide_index: s.title for s in all_slides}
        assert titles[3] == "Inserted"
        assert titles[4] == "Slide 3"  # was index 3, now 4
        assert titles[5] == "Slide 4"  # was index 4, now 5

    async def test_insert_after_first_puts_second(self, d):
        db_obj, outline = d
        slides = await db_obj.get_slides_by_outline_id(outline.id)
        s1 = [s for s in slides if s.slide_index == 1][0]
        new_slide = await db_obj.insert_outline_slide_after(
            outline.id, after_slide_id=s1.id, title="New Second",
        )
        assert new_slide.slide_index == 2
        all_slides = await db_obj.get_slides_by_outline_id(outline.id)
        assert [s.slide_index for s in all_slides] == [1, 2, 3, 4, 5]
        assert all_slides[1].title == "New Second"
