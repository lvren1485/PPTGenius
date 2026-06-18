"""Web search → scrape → index pipeline — singleton service.

- ``search()`` — search engine only, returns {title, url, snippet}. LLM decides which to fetch.
- ``fetch_and_ingest()`` — fetch a single URL, index into KnowledgeService.

Supported engines: duckduckgo (free) | searxng | bing / google / tavily (needs key).
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

from .knowledge import KnowledgeService
from pptgenius.infrastructure.workspace.manager import WorkspaceManager
from .scraper import fetch_page

_log = get_logger("pptgenius.websearch")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


# -- search engine backends --------------------------------------------------

async def _search_duckduckgo(query: str, max_results: int, timeout: int) -> list[dict]:
    url = "https://html.duckduckgo.com/html/?"
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as client:
        resp = await client.post(url, data={"q": query}, follow_redirects=True)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[dict] = []
    for el in soup.select(".result")[:max_results]:
        a = el.select_one(".result__a")
        snippet_el = el.select_one(".result__snippet")
        if not a or not a.get("href"):
            continue
        href = a["href"]
        if href.startswith("//"):
            href = "https:" + href
        results.append({
            "title": a.get_text(strip=True),
            "url": href,
            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
        })
    return results


async def _search_searxng(query: str, max_results: int, timeout: int, base_url: str) -> list[dict]:
    search_url = f"{base_url.rstrip('/')}/search?{urlencode({'q': query, 'format': 'json'})}"
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as client:
        resp = await client.get(search_url)
        resp.raise_for_status()
        data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""),
         "snippet": r.get("content", "") or r.get("snippet", "")}
        for r in data.get("results", [])[:max_results]
    ]


# -- service -----------------------------------------------------------------

class WebSearchService:
    """Web search service (singleton)."""

    _instance: "WebSearchService | None" = None

    def __new__(cls) -> "WebSearchService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialised"):
            return
        self._initialised = True

    # -- public API ----------------------------------------------------------

    async def search(self, query: str, max_results: int | None = None) -> list[dict]:
        """Search the web — returns ``[{title, url, snippet}, ...]``.
        No scraping or indexing. LLM decides which URLs to fetch.
        """
        cfg = get_settings().web_search
        if not cfg.enabled:
            _log.debug("web_search disabled")
            return []
        max_n = max_results if max_results is not None else cfg.max_results
        return await self._do_search(query, max_n, cfg)

    async def fetch_and_ingest(
        self, db: Database, url: str, user_id: int, conv_id: int,
        agent_id: str = "",
    ) -> dict:
        """Fetch a single *url*, scrape its content, and index via KnowledgeService.

        Returns ``{url, title, domain, text, char_count, ingested, knowledge_file_id}``.
        """
        cfg = get_settings().web_search
        sc = await fetch_page(url, cfg.timeout)

        if sc["text"] and len(sc["text"]) > 100:
            sc["ingested"] = True
            sc["knowledge_file_id"] = await self._ingest_result(db, sc, user_id, conv_id)
            # Generate summary after ingest
            if sc["knowledge_file_id"]:
                from .summary import summary_service
                try:
                    await summary_service.summarize_web(
                        db, sc["knowledge_file_id"],
                        title=sc.get("title", ""), url=sc.get("url", url), text=sc["text"],
                        agent_id=agent_id,
                    )
                except Exception:
                    _log.exception("web summary failed for url=%s", url)
        else:
            sc["ingested"] = False
            sc["knowledge_file_id"] = None

        return sc

    # -- internal ------------------------------------------------------------

    async def _do_search(self, query: str, max_n: int, cfg) -> list[dict]:
        engine = cfg.engine
        if engine == "duckduckgo":
            return await _search_duckduckgo(query, max_n, cfg.timeout)
        if engine == "searxng" and cfg.searxng_base_url:
            return await _search_searxng(query, max_n, cfg.timeout, cfg.searxng_base_url)
        _log.warning("unsupported engine '%s' — trying duckduckgo", engine)
        return await _search_duckduckgo(query, max_n, cfg.timeout)

    async def _ingest_result(self, db: Database, result: dict, user_id: int, conv_id: int) -> int | None:
        text = f"# {result['title']}\n\nURL: {result['url']}\n\n{result['text']}"
        safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in result["title"])[:30]
        kdir = WorkspaceManager().get_knowledge_dir(conv_id)
        kdir.mkdir(parents=True, exist_ok=True)
        res_path = kdir / f"web_{int(time.time())}_{safe_title}.txt"
        res_path.write_text(text, encoding="utf-8")
        ks = KnowledgeService()
        file_id = await ks.ingest(db, str(res_path), user_id,
                                  conversation_id=conv_id, source_type="web")
        if file_id:
            _log.debug("indexed %s → file_id=%d", result["url"], file_id)
        return file_id


web_search_service = WebSearchService()
