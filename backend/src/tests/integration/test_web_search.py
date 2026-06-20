"""Test scraper + web search service."""
import pytest
import pytest_asyncio
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.rag.scraper import fetch_page, _clean_text, _extract_title
from pptgenius.infrastructure.rag.web_search import WebSearchService


class TestScraper:
    def test_clean_html(self):
        html = "<html><head><script>js</script></head><body><p>Hello</p><p>World</p></body></html>"
        text = _clean_text(html)
        assert "Hello" in text
        assert "World" in text
        assert "js" not in text

    def test_extract_title(self):
        html = "<html><head><title>My Page</title></head><body></body></html>"
        assert _extract_title(html) == "My Page"

    @pytest.mark.asyncio
    async def test_fetch_invalid_url(self):
        result = await fetch_page("http://localhost:1/doesnotexist", timeout=2)
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_fetch_example_com(self):
        result = await fetch_page("https://example.com", timeout=10)
        if result["char_count"] == 0:
            pytest.skip("network unavailable")
        assert "Example Domain" in result["title"]
        assert result["char_count"] > 50


class TestWebSearchService:
    @pytest_asyncio.fixture
    async def d(self, db):
        db_obj = Database(db)
        user = await db_obj.create_user("ws_user")
        conv = await db_obj.create_conversation(user.id)
        return db_obj, user, conv

    async def test_search(self):
        svc = WebSearchService()
        results = await svc.search("Python programming", max_results=3)
        if not results:
            pytest.skip("DuckDuckGo returned no results")
        assert len(results) <= 3
        for r in results:
            assert r["url"]
            assert r["title"]

    async def test_search_zero_max(self):
        svc = WebSearchService()
        results = await svc.search("test", max_results=0)
        assert results == []

    async def test_fetch_and_ingest(self, db, d):
        """Fetch example.com, ingest, verify searchable."""
        db_obj, user, conv = d
        svc = WebSearchService()
        result = await svc.fetch_and_ingest(db_obj, "https://example.com", user.id, conv.id)
        if result["char_count"] == 0:
            pytest.skip("network unavailable")
        print(f"\n  {result['url']} → {result['char_count']} chars  ingested={result['ingested']}")
        assert result["char_count"] > 50
        assert result["ingested"] is True
        assert result["knowledge_file_id"] is not None

        # Verify via KnowledgeService
        from pptgenius.infrastructure.rag.knowledge import KnowledgeService
        ks = KnowledgeService()
        sr = await ks.search(db_obj, user.id, "Example Domain", top_k=3)
        if sr:
            print(f"  KM search hit: score={sr[0]['score']}  [{len(sr[0]['chunk'])} chars]")
            assert any("Example" in r["chunk"] for r in sr)
