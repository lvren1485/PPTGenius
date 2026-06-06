"""Tests for Phase 0 knowledge file — conversation_id, web_url, summary_json."""

import pytest_asyncio

from pptgenius.infrastructure.db.database import Database


class TestKnowledgeFileNewFields:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("kn_user")
        conv = await Database(db).create_conversation(u.id)
        return Database(db), u, conv

    async def test_create_with_conversation_id(self, d):
        db_obj, user, conv = d
        kf = await db_obj.create_knowledge_file(
            user.id, "test.pdf", "/tmp/test.pdf", "pdf",
            conversation_id=conv.id,
        )
        assert kf.conversation_id == conv.id

    async def test_create_with_web_url(self, d):
        db_obj, user, conv = d
        kf = await db_obj.create_knowledge_file(
            user.id, "web_article", "/tmp/web_article.html", "html",
            source_type="web", web_url="https://example.com/article",
        )
        assert kf.web_url == "https://example.com/article"
        assert kf.source_type == "web"

    async def test_list_by_conversation_id(self, d):
        db_obj, user, conv = d
        conv2 = await db_obj.create_conversation(user.id)
        await db_obj.create_knowledge_file(
            user.id, "file_a.pdf", "/tmp/a.pdf", "pdf",
            conversation_id=conv.id,
        )
        await db_obj.create_knowledge_file(
            user.id, "file_b.pdf", "/tmp/b.pdf", "pdf",
            conversation_id=conv.id,
        )
        await db_obj.create_knowledge_file(
            user.id, "file_c.pdf", "/tmp/c.pdf", "pdf",
            conversation_id=conv2.id,
        )
        files = await db_obj.list_knowledge_files(user.id, conversation_id=conv.id)
        assert len(files) == 2
        assert all(f.conversation_id == conv.id for f in files)

    async def test_duplicate_file_path_returns_existing(self, d):
        db_obj, user, conv = d
        kf1 = await db_obj.create_knowledge_file(
            user.id, "dup.pdf", "/tmp/dup_test.pdf", "pdf",
        )
        kf2 = await db_obj.create_knowledge_file(
            user.id, "dup.pdf", "/tmp/dup_test.pdf", "pdf",
        )
        assert kf1.id == kf2.id

    async def test_update_summary_json(self, d):
        db_obj, user, conv = d
        kf = await db_obj.create_knowledge_file(
            user.id, "summary.pdf", "/tmp/summary.pdf", "pdf",
        )
        summary = {"topics": ["AI", "ML"], "key_data": ["500亿市场"]}
        await db_obj.update_knowledge_file_summary(kf.id, summary)
        fetched = await db_obj.get_knowledge_file(kf.id)
        assert fetched.summary_json == summary
