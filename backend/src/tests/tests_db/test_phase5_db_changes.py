"""Tests for Phase 5 DB changes — single version field, explore_result_json,
presentation version/outline_version, set_outline_title, explore cache, web_url.
"""

import pytest
import pytest_asyncio

from pptgenius.infrastructure.db.database import Database


class TestOutlineSingleVersion:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("v1_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, title="V1 Test")
        return Database(db), o

    async def test_version_defaults_to_1(self, d):
        db_obj, o = d
        assert o.version == 1

    async def test_increase_version(self, d):
        db_obj, o = d
        await db_obj.increase_outline_version(o.id)
        await db_obj.increase_outline_version(o.id)
        fetched = await db_obj.get_outline(o.id)
        assert fetched.version == 3

    async def test_increase_version_no_type_arg(self, d):
        db_obj, o = d
        # Should work without the legacy 'type' argument
        assert await db_obj.increase_outline_version(o.id)
        fetched = await db_obj.get_outline(o.id)
        assert fetched.version == 2

    async def test_no_version_major_fields(self, d):
        db_obj, o = d
        assert not hasattr(o, "version_major")
        assert not hasattr(o, "version_minor")
        assert not hasattr(o, "version_patch")


class TestSetOutlineTitle:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("title_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id)
        return Database(db), o

    async def test_create_with_empty_title(self, d):
        db_obj, o = d
        assert o.title == ""

    async def test_set_title(self, d):
        db_obj, o = d
        assert await db_obj.set_outline_title(o.id, "AI教育报告")
        fetched = await db_obj.get_outline(o.id)
        assert fetched.title == "AI教育报告"

    async def test_set_title_on_deleted_outline(self, d):
        db_obj, o = d
        await db_obj.soft_delete_outline(o.id)
        assert await db_obj.set_outline_title(o.id, "x") is False


class TestOutlineExploreResult:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("explore_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id)
        return Database(db), o

    async def test_set_and_get_explore_result(self, d):
        db_obj, o = d
        result = {
            "run_at": "2026-06-15T10:00:00",
            "sections": [
                {"title": "市场分析", "knowledge_file_ids": [1, 2]},
                {"title": "技术架构", "knowledge_file_ids": [3]},
            ],
        }
        assert await db_obj.set_outline_explore_result(o.id, result)
        stored = await db_obj.get_outline_explore_result(o.id)
        assert stored == result

    async def test_get_explore_result_none(self, d):
        db_obj, o = d
        assert await db_obj.get_outline_explore_result(o.id) is None

    async def test_explore_result_on_deleted_outline(self, d):
        db_obj, o = d
        await db_obj.soft_delete_outline(o.id)
        assert await db_obj.set_outline_explore_result(o.id, {}) is False
        assert await db_obj.get_outline_explore_result(o.id) is None


class TestPresentationVersion:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("pres_ver_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, "PV Test")
        return Database(db), u, conv, o

    async def test_create_presentation_with_outline_version(self, d):
        db_obj, u, conv, o = d
        outline = await db_obj.get_outline(o.id)  # version = 1
        pres = await db_obj.create_presentation(
            u.id, conv.id, outline_id=o.id, outline_version=outline.version,
        )
        assert pres.version == 1
        assert pres.outline_version == 1

    async def test_default_outline_version_zero(self, d):
        db_obj, u, conv, o = d
        pres = await db_obj.create_presentation(
            u.id, conv.id, outline_id=o.id,
        )
        assert pres.outline_version == 0

    async def test_increment_presentation_version(self, d):
        db_obj, u, conv, o = d
        pres = await db_obj.create_presentation(u.id, conv.id, outline_id=o.id)
        assert await db_obj.increment_presentation_version(pres.id)
        assert await db_obj.increment_presentation_version(pres.id)
        fetched = await db_obj.get_presentation(pres.id)
        assert fetched.version == 3

    async def test_increment_on_deleted_presentation(self, d):
        db_obj, u, conv, o = d
        pres = await db_obj.create_presentation(u.id, conv.id, outline_id=o.id)
        await db_obj.soft_delete_presentation(pres.id)
        assert await db_obj.increment_presentation_version(pres.id) is False


class TestKnowledgeFileWebUrl:
    @pytest.mark.asyncio
    async def test_set_web_url(self, db):
        d = Database(db)
        u = await d.create_user("kfwu_user")
        kf = await d.create_knowledge_file(
            u.id, filename="test.txt", file_path="/tmp/test.txt", file_type="txt",
        )
        assert await d.set_knowledge_file_web_url(kf.id, "https://example.com")
        fetched = await d.get_knowledge_file(kf.id)
        assert fetched.web_url == "https://example.com"

    @pytest.mark.asyncio
    async def test_set_web_url_nonexistent_file(self, db):
        d = Database(db)
        assert await d.set_knowledge_file_web_url(99999, "https://x.com") is False


class TestOutlineSlideStatusExtended:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("flag_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, "Flag Test")
        slide = await Database(db).create_outline_slide(o.id, 1, "Slide 1")
        return Database(db), slide

    async def test_status_default_pending(self, d):
        db_obj, slide = d
        assert slide.status == "pending"

    async def test_status_to_merge(self, d):
        db_obj, slide = d
        await db_obj.update_outline_slide_status(slide.id, "merge")
        fetched = await db_obj.get_outline_slide(slide.id)
        assert fetched.status == "merge"

    async def test_status_to_modify(self, d):
        db_obj, slide = d
        await db_obj.update_outline_slide_status(slide.id, "modify")
        fetched = await db_obj.get_outline_slide(slide.id)
        assert fetched.status == "modify"

    async def test_status_to_completed(self, d):
        db_obj, slide = d
        await db_obj.update_outline_slide_status(slide.id, "completed")
        fetched = await db_obj.get_outline_slide(slide.id)
        assert fetched.status == "completed"
