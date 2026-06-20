"""Tests for simplified RAG — build_index + search, 4 modes, filter_web."""

import pytest

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.rag.bm25 import BM25Manager
from pptgenius.infrastructure.rag.knowledge import knowledge_service


async def _seed_files(d: Database, user_id: int, conv_id: int, prefix: str = ""):
    p = f"{prefix}_" if prefix else ""
    kf1 = await d.create_knowledge_file(user_id, f"{p}upload_a.txt", f"/tmp/{p}upload_a.txt", "txt", conversation_id=conv_id, source_type="upload")
    kf2 = await d.create_knowledge_file(user_id, f"{p}upload_b.txt", f"/tmp/{p}upload_b.txt", "txt", conversation_id=conv_id, source_type="upload")
    kf_web = await d.create_knowledge_file(user_id, f"{p}web_page.txt", f"/tmp/{p}web_page.txt", "txt", conversation_id=conv_id, source_type="web")
    await d.create_chunk(kf1.id, 0, "人工智能市场规模持续增长 预计2026年达到万亿级别")
    await d.create_chunk(kf2.id, 0, "机器学习算法在医疗诊断中表现优异")
    await d.create_chunk(kf_web.id, 0, "网络搜索结果显示AI投资热度不减")
    return kf1, kf2, kf_web


class TestSettingsRepo:
    @pytest.mark.asyncio
    async def test_defaults(self, db):
        d = Database(db)
        u = await d.create_user("s_default")
        assert await d.get_rag_mode(u.id) == "user"
        assert await d.get_web_search_enabled(u.id) is True

    @pytest.mark.asyncio
    async def test_set_both(self, db):
        d = Database(db)
        u = await d.create_user("s_both")
        await d.set_rag_mode(u.id, "conversation")
        await d.set_web_search_enabled(u.id, False)
        assert await d.get_rag_mode(u.id) == "conversation"
        assert await d.get_web_search_enabled(u.id) is False


class TestFilterWebChunks:
    @pytest.mark.asyncio
    async def test_user_filter_web(self, db):
        d = Database(db)
        u = await d.create_user("fw_user")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="fw1")
        all_c = await d.get_all_chunks_for_user(u.id)
        filtered = await d.get_chunks_for_user_filter_web(u.id)
        assert len(all_c) == 3
        assert len(filtered) == 2
        for c in filtered:
            assert "网络搜索" not in c.chunk_text

    @pytest.mark.asyncio
    async def test_conv_filter_web(self, db):
        d = Database(db)
        u = await d.create_user("fw_conv")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="fw2")
        all_c = await d.get_all_chunks_for_conversation(conv.id)
        filtered = await d.get_chunks_for_conversation_filter_web(conv.id)
        assert len(all_c) == 3
        assert len(filtered) == 2


class TestSearchFourModes:
    @pytest.mark.asyncio
    async def test_mode_user_web_on(self, db):
        d = Database(db)
        u = await d.create_user("m1")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="m1")
        scope = await knowledge_service.build_index(d, user_id=u.id, rag_mode="user", filter_web=False)
        results = await knowledge_service.search(d, u.id, "AI 市场")
        assert len(results) == 3
        assert any("网络搜索" in r["chunk"] for r in results)

    @pytest.mark.asyncio
    async def test_mode_user_web_off(self, db):
        d = Database(db)
        u = await d.create_user("m2")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="m2")
        await knowledge_service.build_index(d, user_id=u.id, rag_mode="user", filter_web=True)
        results = await knowledge_service.search(d, u.id, "AI 市场")
        assert len(results) == 2
        assert not any("网络搜索" in r["chunk"] for r in results)

    @pytest.mark.asyncio
    async def test_mode_conv_web_on(self, db):
        d = Database(db)
        u = await d.create_user("m3")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="m3")
        await knowledge_service.build_index(d, user_id=u.id, rag_mode="conversation", filter_web=False, conversation_id=conv.id)
        results = await knowledge_service.search_by_conversation(d, conv.id, "AI")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_mode_conv_web_off(self, db):
        d = Database(db)
        u = await d.create_user("m4")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="m4")
        await knowledge_service.build_index(d, user_id=u.id, rag_mode="conversation", filter_web=True, conversation_id=conv.id)
        results = await knowledge_service.search_by_conversation(d, conv.id, "AI")
        assert len(results) == 2
        assert not any("网络搜索" in r["chunk"] for r in results)

    @pytest.mark.asyncio
    async def test_index_isolation_across_users(self, db):
        d = Database(db)
        u_a = await d.create_user("iso_a")
        u_b = await d.create_user("iso_b")
        conv_a = await d.create_conversation(u_a.id)
        conv_b = await d.create_conversation(u_b.id)
        await _seed_files(d, u_a.id, conv_a.id, prefix="iso_a")
        await _seed_files(d, u_b.id, conv_b.id, prefix="iso_b")
        await knowledge_service.build_index(d, user_id=u_a.id, rag_mode="user", filter_web=False)
        results = await knowledge_service.search(d, u_a.id, "市场规模 医疗 网络")
        assert len(results) == 3  # user A only sees own 3 files

    @pytest.mark.asyncio
    async def test_remove_index(self, db):
        d = Database(db)
        u = await d.create_user("rm")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="rm")
        scope = await knowledge_service.build_index(d, user_id=u.id, rag_mode="user", filter_web=False)
        results = await knowledge_service.search(d, u.id, "AI")
        assert len(results) == 3
        knowledge_service.remove_index(scope)
        # After removal, search falls back to on-demand build
        results = await knowledge_service.search(d, u.id, "AI")
        assert len(results) == 3


class TestSearchByConversation:
    @pytest.mark.asyncio
    async def test_search_empty(self, db):
        d = Database(db)
        u = await d.create_user("ks_empty")
        conv = await d.create_conversation(u.id)
        await knowledge_service.build_index(d, user_id=u.id, rag_mode="conversation", filter_web=False, conversation_id=conv.id)
        results = await knowledge_service.search_by_conversation(d, conv.id, "test")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_results(self, db):
        d = Database(db)
        u = await d.create_user("ks_user")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(u.id, "doc.txt", "/tmp/ks_doc.txt", "txt", conversation_id=conv.id)
        await d.create_chunk(kf.id, 0, "人工智能市场规模达500亿")
        await knowledge_service.build_index(d, user_id=u.id, rag_mode="conversation", filter_web=False, conversation_id=conv.id)
        results = await knowledge_service.search_by_conversation(d, conv.id, "AI 市场")
        assert len(results) >= 1
        assert any("500亿" in r["chunk"] for r in results)

    @pytest.mark.asyncio
    async def test_search_isolated(self, db):
        d = Database(db)
        u = await d.create_user("ks_iso")
        conv_a = await d.create_conversation(u.id)
        conv_b = await d.create_conversation(u.id)
        for conv, text in [(conv_a, "AAA专属"), (conv_b, "BBB专属")]:
            kf = await d.create_knowledge_file(u.id, f"{text}.txt", f"/tmp/{text}.txt", "txt", conversation_id=conv.id)
            await d.create_chunk(kf.id, 0, text)
        await knowledge_service.build_index(d, user_id=u.id, rag_mode="conversation", filter_web=False, conversation_id=conv_a.id)
        r_a = await knowledge_service.search_by_conversation(d, conv_a.id, "AAA")
        assert any("AAA" in r["chunk"] for r in r_a)


class TestBuildChunkMap:
    @pytest.mark.asyncio
    async def test_user_mode(self, db):
        from pptgenius.agent.outline.knowledge_tools import _build_chunk_map
        d = Database(db)
        u = await d.create_user("bcm1")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="bcm1")
        cmap = await _build_chunk_map(d, u.id, conv.id, "user", filter_web=False)
        assert len(cmap) == 3

    @pytest.mark.asyncio
    async def test_user_mode_filter_web(self, db):
        from pptgenius.agent.outline.knowledge_tools import _build_chunk_map
        d = Database(db)
        u = await d.create_user("bcm2")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="bcm2")
        cmap = await _build_chunk_map(d, u.id, conv.id, "user", filter_web=True)
        assert len(cmap) == 2

    @pytest.mark.asyncio
    async def test_conv_mode(self, db):
        from pptgenius.agent.outline.knowledge_tools import _build_chunk_map
        d = Database(db)
        u = await d.create_user("bcm3")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="bcm3")
        cmap = await _build_chunk_map(d, u.id, conv.id, "conversation", filter_web=False)
        assert len(cmap) == 3

    @pytest.mark.asyncio
    async def test_conv_mode_filter_web(self, db):
        from pptgenius.agent.outline.knowledge_tools import _build_chunk_map
        d = Database(db)
        u = await d.create_user("bcm4")
        conv = await d.create_conversation(u.id)
        await _seed_files(d, u.id, conv.id, prefix="bcm4")
        cmap = await _build_chunk_map(d, u.id, conv.id, "conversation", filter_web=True)
        assert len(cmap) == 2


class TestBM25Manager:
    def test_persist_false_no_file(self, tmp_path):
        bm = BM25Manager(tmp_path / "g.pkl", persist=False)
        bm.build(["hello world", "foo bar"])
        bm.save()
        assert not (tmp_path / "g.pkl").exists()

    def test_persist_false_search(self, tmp_path):
        bm = BM25Manager(tmp_path / "g.pkl", persist=False)
        bm.build(["apple orange banana", "cat dog mouse", "red blue green"])
        results = bm.search("apple fruit", top_k=2)
        assert len(results) == 2
        assert "apple" in results[0]["chunk"]

    def test_persist_true_save_load(self, tmp_path):
        bm = BM25Manager(tmp_path / "real.pkl", persist=True)
        bm.build(["hello world"])
        bm.save()
        assert (tmp_path / "real.pkl").exists()
        bm2 = BM25Manager(tmp_path / "real.pkl", persist=True)
        assert bm2.load() is True

    def test_empty_build(self, tmp_path):
        bm = BM25Manager(tmp_path / "e.pkl", persist=False)
        bm.build([])
        assert bm.search("anything") == []
