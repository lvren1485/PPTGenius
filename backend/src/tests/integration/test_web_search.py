"""Test scraper + web search service — DuckDuckGo & SearXNG."""
import pytest
import pytest_asyncio
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.rag.scraper import fetch_page, _clean_text, _extract_title
from pptgenius.infrastructure.rag.web_search import (
    WebSearchService,
    _search_duckduckgo,
    _search_searxng,
)


def is_searxng_configured() -> bool:
    """Return True if SearXNG is configured and should be tested."""
    cfg = get_settings().web_search
    return cfg.engine == "searxng" and bool(cfg.searxng_base_url)


def _validate_result_structure(r: dict) -> None:
    """Verify a search result has the required {title, url, snippet} shape."""
    assert isinstance(r, dict), f"result must be dict, got {type(r)}"
    assert "title" in r, "result missing 'title'"
    assert "url" in r, "result missing 'url'"
    assert "snippet" in r, "result missing 'snippet'"
    assert isinstance(r["title"], str)
    assert isinstance(r["url"], str)
    assert isinstance(r["snippet"], str)
    assert r["url"], "url must not be empty"


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
        try:
            results = await svc.search("Python programming", max_results=3)
        except Exception as e:
            pytest.skip(f"search unreachable: {e}")
        if not results:
            pytest.skip("search returned no results")
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


# ═══════════════════════════════════════════════════════════════════════
# Engine comparison — DuckDuckGo vs SearXNG result structure consistency
# ═══════════════════════════════════════════════════════════════════════


class TestDuckDuckGoStructure:
    """Verify DuckDuckGo returns correct result structure."""

    @pytest.mark.asyncio
    async def test_result_shape(self):
        try:
            results = await _search_duckduckgo("Python", max_results=3, timeout=10)
        except Exception as e:
            pytest.skip(f"DuckDuckGo unreachable: {e}")
        if not results:
            pytest.skip("DuckDuckGo returned no results (network / captcha)")
        for r in results:
            _validate_result_structure(r)

    @pytest.mark.asyncio
    async def test_max_results_respected(self):
        try:
            results = await _search_duckduckgo("hello world", max_results=2, timeout=10)
        except Exception as e:
            pytest.skip(f"DuckDuckGo unreachable: {e}")
        assert len(results) <= 2


@pytest.mark.skipif(
    not is_searxng_configured(),
    reason="SearXNG not configured (set engine=searxng and searxng_base_url)",
)
class TestSearXNGStructure:
    """Verify SearXNG returns correct result structure (only when configured)."""

    @pytest.mark.asyncio
    async def test_result_shape(self):
        cfg = get_settings().web_search
        results = await _search_searxng("Python", max_results=3,
                                         timeout=cfg.timeout,
                                         base_url=cfg.searxng_base_url)
        if not results:
            pytest.skip("SearXNG returned no results")
        for r in results:
            _validate_result_structure(r)

    @pytest.mark.asyncio
    async def test_max_results_respected(self):
        cfg = get_settings().web_search
        results = await _search_searxng("hello", max_results=2,
                                         timeout=cfg.timeout,
                                         base_url=cfg.searxng_base_url)
        assert len(results) <= 2


class TestEngineComparison:
    """Compare DuckDuckGo and SearXNG result structures for consistency."""

    QUERY = "Python programming language"

    @pytest.mark.asyncio
    async def test_both_engines_same_structure(self):
        """Both engines must return [{title, url, snippet}, ...]."""
        try:
            ddg = await _search_duckduckgo(self.QUERY, max_results=3, timeout=10)
        except Exception:
            ddg = []
        if not ddg:
            pytest.skip("DuckDuckGo unavailable")

        if not is_searxng_configured():
            pytest.skip("SearXNG not configured")

        cfg = get_settings().web_search
        srx = await _search_searxng(self.QUERY, max_results=3,
                                     timeout=cfg.timeout,
                                     base_url=cfg.searxng_base_url)
        if not srx:
            pytest.skip("SearXNG unavailable")

        # Both must return list[dict]
        assert isinstance(ddg, list)
        assert isinstance(srx, list)

        # Both must have same keys
        for r in ddg:
            _validate_result_structure(r)
        for r in srx:
            _validate_result_structure(r)

        print(f"\n  DuckDuckGo: {len(ddg)} results")
        print(f"  SearXNG:    {len(srx)} results")
        print(f"  DDG[0]:     {ddg[0]['title'][:50]}")
        print(f"  SRX[0]:     {srx[0]['title'][:50] if srx else 'N/A'}")

    @pytest.mark.asyncio
    async def test_public_api_uses_configured_engine(self):
        """WebSearchService.search() delegates to the configured engine."""
        svc = WebSearchService()
        results = await svc.search(self.QUERY, max_results=2)
        if not results:
            pytest.skip("search returned no results")
        for r in results:
            _validate_result_structure(r)

    @pytest.mark.asyncio
    async def test_search_disabled(self, monkeypatch):
        """When enabled=False, search returns empty list."""
        from pptgenius.infrastructure.config.models import WebSearchConfig
        cfg = get_settings()
        original = cfg.web_search
        cfg.web_search = WebSearchConfig(enabled=False)
        try:
            svc = WebSearchService()
            results = await svc.search("test")
            assert results == []
        finally:
            cfg.web_search = original
