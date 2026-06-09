"""Tests for RAG dual-mode — user-level (persisted) vs conversation-level (in-memory) BM25."""

import pytest

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.rag.bm25 import BM25Manager
from pptgenius.infrastructure.rag.knowledge import KnowledgeService, knowledge_service


# ── User repo: rag_mode ──────────────────────────────────────────────────────


class TestRagMode:
    @pytest.mark.asyncio
    async def test_default_rag_mode_is_user(self, db):
        d = Database(db)
        u = await d.create_user("rag_default")
        assert await d.get_rag_mode(u.id) == "user"

    @pytest.mark.asyncio
    async def test_set_and_get_rag_mode_conversation(self, db):
        d = Database(db)
        u = await d.create_user("rag_conv")
        ok = await d.set_rag_mode(u.id, "conversation")
        assert ok is True
        assert await d.get_rag_mode(u.id) == "conversation"

    @pytest.mark.asyncio
    async def test_set_rag_mode_user(self, db):
        d = Database(db)
        u = await d.create_user("rag_user2")
        await d.set_rag_mode(u.id, "conversation")
        await d.set_rag_mode(u.id, "user")
        assert await d.get_rag_mode(u.id) == "user"

    @pytest.mark.asyncio
    async def test_set_rag_mode_invalid(self, db):
        d = Database(db)
        u = await d.create_user("rag_invalid")
        ok = await d.set_rag_mode(u.id, "invalid")
        assert ok is False
        assert await d.get_rag_mode(u.id) == "user"

    @pytest.mark.asyncio
    async def test_set_rag_mode_nonexistent_user(self, db):
        d = Database(db)
        ok = await d.set_rag_mode(99999, "conversation")
        assert ok is False

    @pytest.mark.asyncio
    async def test_get_rag_mode_nonexistent_user(self, db):
        d = Database(db)
        assert await d.get_rag_mode(99999) == "user"

    @pytest.mark.asyncio
    async def test_update_user_other(self, db):
        d = Database(db)
        u = await d.create_user("other_user")
        await d.update_user_other(u.id, {"rag_mode": "conversation", "theme": "dark"})
        user = await d.get_user(u.id)
        assert user.other == {"rag_mode": "conversation", "theme": "dark"}

    @pytest.mark.asyncio
    async def test_rag_mode_preserved_in_other(self, db):
        d = Database(db)
        u = await d.create_user("rag_preserved", other={"custom_key": "val"})
        await d.set_rag_mode(u.id, "conversation")
        user = await d.get_user(u.id)
        assert user.other["custom_key"] == "val"
        assert user.other["rag_mode"] == "conversation"


# ── Knowledge repo: conversation chunks ─────────────────────────────────────


class TestConversationChunks:
    @pytest.mark.asyncio
    async def test_get_chunks_for_conversation_empty(self, db):
        d = Database(db)
        u = await d.create_user("cc_empty")
        conv = await d.create_conversation(u.id)
        chunks = await d.get_all_chunks_for_conversation(conv.id)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_get_chunks_for_conversation(self, db):
        d = Database(db)
        u = await d.create_user("cc_user")
        conv = await d.create_conversation(u.id)
        conv2 = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(
            u.id, "f1.txt", "/tmp/f1.txt", "txt",
            conversation_id=conv.id,
        )
        kf2 = await d.create_knowledge_file(
            u.id, "f2.txt", "/tmp/f2.txt", "txt",
            conversation_id=conv2.id,
        )
        await d.create_chunk(kf.id, 0, "conv1 chunk a")
        await d.create_chunk(kf.id, 1, "conv1 chunk b")
        await d.create_chunk(kf2.id, 0, "conv2 chunk")

        chunks = await d.get_all_chunks_for_conversation(conv.id)
        assert len(chunks) == 2
        texts = {c.chunk_text for c in chunks}
        assert texts == {"conv1 chunk a", "conv1 chunk b"}

    @pytest.mark.asyncio
    async def test_get_chunks_isolated_per_conversation(self, db):
        d = Database(db)
        u = await d.create_user("cc_isolated")
        conv_a = await d.create_conversation(u.id)
        conv_b = await d.create_conversation(u.id)

        for conv, label in [(conv_a, "A"), (conv_b, "B")]:
            kf = await d.create_knowledge_file(
                u.id, f"f_{label}.txt", f"/tmp/f_{label}.txt", "txt",
                conversation_id=conv.id,
            )
            await d.create_chunk(kf.id, 0, f"chunk_{label}")

        chunks_a = await d.get_all_chunks_for_conversation(conv_a.id)
        chunks_b = await d.get_all_chunks_for_conversation(conv_b.id)
        assert len(chunks_a) == 1 and chunks_a[0].chunk_text == "chunk_A"
        assert len(chunks_b) == 1 and chunks_b[0].chunk_text == "chunk_B"


# ── BM25Manager: persist=False ──────────────────────────────────────────────


class TestBM25ManagerMemoryOnly:
    def test_persist_false_no_file_created(self, tmp_path):
        bm = BM25Manager(tmp_path / "ghost.pkl", persist=False)
        bm.build(["hello world", "foo bar"])
        bm.save()  # no-op
        assert not (tmp_path / "ghost.pkl").exists()

    def test_persist_false_load_returns_false(self, tmp_path):
        bm = BM25Manager(tmp_path / "ghost.pkl", persist=False)
        assert bm.load() is False

    def test_persist_false_search_works(self, tmp_path):
        bm = BM25Manager(tmp_path / "ghost.pkl", persist=False)
        bm.build(["apple orange banana", "cat dog mouse", "red blue green"])
        results = bm.search("apple fruit", top_k=2)
        assert len(results) == 2
        assert "apple" in results[0]["chunk"]

    def test_persist_true_saves_file(self, tmp_path):
        bm = BM25Manager(tmp_path / "real.pkl", persist=True)
        bm.build(["hello world"])
        bm.save()
        assert (tmp_path / "real.pkl").exists()
        bm2 = BM25Manager(tmp_path / "real.pkl", persist=True)
        assert bm2.load() is True
        assert bm2.chunk_count == 1

    def test_persist_default_is_true(self, tmp_path):
        bm = BM25Manager(tmp_path / "default.pkl")
        assert bm.persist is True

    def test_empty_build_no_error(self, tmp_path):
        bm = BM25Manager(tmp_path / "empty.pkl", persist=False)
        bm.build([])
        assert bm.search("anything") == []


# ── KnowledgeService: conversation-level search ─────────────────────────────


class TestKnowledgeServiceConvSearch:
    @pytest.mark.asyncio
    async def test_search_by_conversation_empty(self, db):
        d = Database(db)
        u = await d.create_user("ks_empty")
        conv = await d.create_conversation(u.id)
        results = await knowledge_service.search_by_conversation(d, conv.id, "test")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_by_conversation_returns_results(self, db):
        d = Database(db)
        u = await d.create_user("ks_user")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(
            u.id, "doc.txt", "/tmp/ks_doc.txt", "txt",
            conversation_id=conv.id,
        )
        await d.create_chunk(kf.id, 0, "人工智能市场规模达500亿")
        await d.create_chunk(kf.id, 1, "机器学习是核心驱动力")
        results = await knowledge_service.search_by_conversation(d, conv.id, "AI 市场")
        assert len(results) >= 1
        assert any("500亿" in r["chunk"] for r in results)

    @pytest.mark.asyncio
    async def test_search_by_conversation_caches_index(self, db):
        d = Database(db)
        u = await d.create_user("ks_cache")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(
            u.id, "cache.txt", "/tmp/cache.txt", "txt",
            conversation_id=conv.id,
        )
        await d.create_chunk(kf.id, 0, "缓存测试内容")
        # First call builds and caches index
        await knowledge_service.search_by_conversation(d, conv.id, "缓存")
        assert conv.id in knowledge_service._conv_indexes

    @pytest.mark.asyncio
    async def test_search_by_conversation_empty_no_cache(self, db):
        d = Database(db)
        u = await d.create_user("ks_nocache")
        conv = await d.create_conversation(u.id)
        results = await knowledge_service.search_by_conversation(d, conv.id, "test")
        assert results == []
        # Empty conversation doesn't cache
        assert conv.id not in knowledge_service._conv_indexes

    @pytest.mark.asyncio
    async def test_rebuild_conversation_index(self, db):
        d = Database(db)
        u = await d.create_user("ks_rebuild")
        conv = await d.create_conversation(u.id)
        # Initial: empty
        await knowledge_service.search_by_conversation(d, conv.id, "AI")
        # Add chunks
        kf = await d.create_knowledge_file(
            u.id, "new.txt", "/tmp/ks_new.txt", "txt",
            conversation_id=conv.id,
        )
        await d.create_chunk(kf.id, 0, "新添加的AI内容")
        # Rebuild
        await knowledge_service.rebuild_conversation_index(d, conv.id)
        results = await knowledge_service.search_by_conversation(d, conv.id, "AI")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_rebuild_empty_conversation_removes_cache(self, db):
        d = Database(db)
        u = await d.create_user("ks_rem")
        conv = await d.create_conversation(u.id)
        # Create cache entry
        kf = await d.create_knowledge_file(
            u.id, "tmp.txt", "/tmp/ks_tmp.txt", "txt",
            conversation_id=conv.id,
        )
        await d.create_chunk(kf.id, 0, "stuff")
        await knowledge_service.rebuild_conversation_index(d, conv.id)
        assert conv.id in knowledge_service._conv_indexes
        # Delete file, rebuild → empty
        await d.delete_knowledge_file(kf.id)
        await knowledge_service.rebuild_conversation_index(d, conv.id)
        assert conv.id not in knowledge_service._conv_indexes

    @pytest.mark.asyncio
    async def test_remove_conversation_index(self, db):
        d = Database(db)
        u = await d.create_user("ks_remove")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(
            u.id, "d.txt", "/tmp/ks_d.txt", "txt", conversation_id=conv.id,
        )
        await d.create_chunk(kf.id, 0, "content")
        await knowledge_service.search_by_conversation(d, conv.id, "content")
        knowledge_service.remove_conversation_index(conv.id)
        assert conv.id not in knowledge_service._conv_indexes

    @pytest.mark.asyncio
    async def test_search_by_conversation_isolated(self, db):
        d = Database(db)
        u = await d.create_user("ks_iso")
        conv_a = await d.create_conversation(u.id)
        conv_b = await d.create_conversation(u.id)

        for conv, text in [(conv_a, "AAA专属"), (conv_b, "BBB专属")]:
            kf = await d.create_knowledge_file(
                u.id, f"{text}.txt", f"/tmp/{text}.txt", "txt",
                conversation_id=conv.id,
            )
            await d.create_chunk(kf.id, 0, text)

        r_a = await knowledge_service.search_by_conversation(d, conv_a.id, "AAA")
        r_b = await knowledge_service.search_by_conversation(d, conv_b.id, "BBB")
        assert any("AAA" in r["chunk"] for r in r_a)
        assert any("BBB" in r["chunk"] for r in r_b)


# ── Generator: _build_chunk_map dual-mode ───────────────────────────────────


class TestBuildChunkMap:
    @pytest.mark.asyncio
    async def test_build_chunk_map_user_mode(self, db):
        from pptgenius.agent.outline.generator import _build_chunk_map

        d = Database(db)
        u = await d.create_user("bcm_user")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(
            u.id, "u.txt", "/tmp/bcm_u.txt", "txt", conversation_id=conv.id,
        )
        await d.create_chunk(kf.id, 0, "ABCDEFGHIJ1234567890_user_content")
        cmap = await _build_chunk_map(d, u.id, conv.id, "user")
        assert len(cmap) == 1
        cid, fid = list(cmap.values())[0]
        assert cid is not None
        assert fid == kf.id

    @pytest.mark.asyncio
    async def test_build_chunk_map_conversation_mode(self, db):
        from pptgenius.agent.outline.generator import _build_chunk_map

        d = Database(db)
        u = await d.create_user("bcm_conv")
        conv = await d.create_conversation(u.id)
        conv2 = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(
            u.id, "c.txt", "/tmp/bcm_c.txt", "txt", conversation_id=conv.id,
        )
        kf2 = await d.create_knowledge_file(
            u.id, "c2.txt", "/tmp/bcm_c2.txt", "txt", conversation_id=conv2.id,
        )
        await d.create_chunk(kf.id, 0, "ABCDEFGHIJ1234567890_conv_content")
        await d.create_chunk(kf2.id, 0, "ABCDEFGHIJ9876543210_other_conv")

        cmap = await _build_chunk_map(d, u.id, conv.id, "conversation")
        assert len(cmap) == 1
        _, fid = list(cmap.values())[0]
        assert fid == kf.id

    @pytest.mark.asyncio
    async def test_build_chunk_map_key_is_first_20_chars(self, db):
        from pptgenius.agent.outline.generator import _build_chunk_map

        d = Database(db)
        u = await d.create_user("bcm_key")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(
            u.id, "key.txt", "/tmp/bcm_key.txt", "txt", conversation_id=conv.id,
        )
        full_text = "ABCDEFGHIJ1234567890_tail_that_should_not_matter"
        await d.create_chunk(kf.id, 0, full_text)
        cmap = await _build_chunk_map(d, u.id, conv.id, "user")
        assert full_text not in cmap
        assert full_text[:20] in cmap
