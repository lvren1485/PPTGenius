"""Shared knowledge tools — used by Generator and Knowledge Agent."""

from __future__ import annotations

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.rag import KnowledgeService, WebSearchService
from pptgenius.infrastructure.utils import get_logger

_log = get_logger(__name__)

_web_search = WebSearchService()
_knowledge = KnowledgeService()

_KB_SEARCH_LIMIT = 9
_WEB_SEARCH_LIMIT = 6
_FETCH_LIMIT = 4
_READ_LIMIT = 3
_EXPLORE_KB_LIMIT = 12
_EXPLORE_WEB_LIMIT = 8
_EXPLORE_FETCH_LIMIT = 6

_LIMIT_HINT = "已达调用上限，请使用其他工具或基于已有信息输出结果。"


async def _build_chunk_map(
    db: Database,
    user_id: int,
    conversation_id: int,
    rag_mode: str,
    filter_web: bool = False,
) -> dict[str, tuple[int, int]]:
    """Return {chunk_text[:20]: (chunk_id, file_id)} for the active scope."""
    if rag_mode == "conversation":
        if filter_web:
            chunks = await db.get_chunks_for_conversation_filter_web(conversation_id)
        else:
            chunks = await db.get_all_chunks_for_conversation(conversation_id)
    else:
        if filter_web:
            chunks = await db.get_chunks_for_user_filter_web(user_id)
        else:
            chunks = await db.get_all_chunks_for_user(user_id)
    return {c.chunk_text[:20]: (c.id, c.file_id) for c in chunks}


def make_search_knowledge(
    db: Database,
    user_id: int,
    conversation_id: int,
    rag_mode: str,
    count: list[int],
    filter_web: bool = False,
    limit: int = _KB_SEARCH_LIMIT,
):
    _chunk_map: dict[str, tuple[int, int]] | None = None

    async def _ensure_map():
        nonlocal _chunk_map
        if _chunk_map is None:
            _chunk_map = await _build_chunk_map(db, user_id, conversation_id,
                                                 rag_mode, filter_web=filter_web)

    @tool
    async def search_knowledge(query: str, top_k: int = 5) -> str:
        """Search the user's personal knowledge base (BM25) for relevant documents.

        Use this first before searching the open web. Max 9 calls per round.
        Each result includes a chunk_id for citation.
        """
        if count[0] >= limit:
            return f"知识库搜索已达上限 ({limit}次)。{_LIMIT_HINT}"
        count[0] += 1

        await _ensure_map()

        if rag_mode == "conversation":
            results = await _knowledge.search_by_conversation(
                db, conversation_id, query, top_k, filter_web=filter_web,
            )
        else:
            results = await _knowledge.search(
                db, user_id, query, top_k, filter_web=filter_web,
            )

        if not results:
            return "知识库中未找到相关文档。"
        items = []
        for r in results:
            chunk_text = r.get("chunk", r.get("text", ""))
            cid, fid = _chunk_map.get(chunk_text[:20], (None, None))
            items.append(
                f"[score={r.get('score', 0):.2f}] "
                f"chunk_id={cid} file_id={fid}\n"
                f"{chunk_text[:500]}"
            )
        return "\n\n---\n".join(items)

    return search_knowledge


def make_search_web(count: list[int], enabled: bool = True,
                    limit: int = _WEB_SEARCH_LIMIT):
    @tool
    async def search_web(query: str, max_results: int = 5) -> str:
        """Search the web for information. Returns title, URL, and snippet.

        Use this when the knowledge base doesn't have enough information.
        """
        if not enabled:
            return "网络搜索已关闭。"
        if count[0] >= limit:
            return f"网络搜索已达上限 ({limit}次)。{_LIMIT_HINT}"
        count[0] += 1

        try:
            results = await _web_search.search(query, max_results)
        except Exception as e:
            _log.warning("web search failed: %s", e)
            return f"网络搜索失败: {e}。可尝试换关键词。"
        if not results:
            return "未找到相关网络结果。"
        items = []
        for i, r in enumerate(results):
            items.append(f"{i+1}. **{r['title']}**\n   URL: {r['url']}\n   {r['snippet']}")
        return "\n\n".join(items)

    return search_web


def make_fetch_web(db: Database, user_id: int, conv_id: int,
                   count: list[int], agent_id: str = "", enabled: bool = True,
                   limit: int = _FETCH_LIMIT):
    @tool
    async def fetch_web(url: str) -> str:
        """Fetch and index a web page. The content is added to the knowledge base.

        Use after search_web to read a promising result.
        """
        if not enabled:
            return "网络抓取已关闭。"
        if count[0] >= limit:
            return f"网页抓取已达上限 ({limit}次)。{_LIMIT_HINT}"
        count[0] += 1
        try:
            result = await _web_search.fetch_and_ingest(
                db, url, user_id, conv_id, agent_id=agent_id,
            )
        except Exception as e:
            _log.warning("web fetch failed: %s — %s", url, e)
            return f"网页抓取失败: {e}。请尝试其他搜索结果。"
        if result.get("ingested"):
            file_id = result.get("knowledge_file_id")
            title = result.get("title", url)
            summary = ""
            if file_id:
                kf = await db.get_knowledge_file(file_id)
                if kf and kf.summary_json:
                    summary = kf.summary_json
            info = f"file_id={file_id}, title={title}"
            if summary:
                info += f"\n摘要: {summary}"
            return f"已抓取并入库。{info}"
        return f"抓取失败。{result.get('title', 'N/A')}"

    return fetch_web


def make_read_file(db: Database, count: list[int], fetched_ids: set[int]):
    @tool
    async def read_file(file_id: int) -> str:
        """Read full content of a knowledge file. Max 3 per round."""
        if count[0] >= _READ_LIMIT:
            return f"文件读取已达上限 ({_READ_LIMIT}次)。{_LIMIT_HINT}"
        if file_id in fetched_ids:
            return f"already fetched (file_id={file_id})"
        count[0] += 1
        fetched_ids.add(file_id)
        chunks = await db.list_chunks_by_file(file_id)
        if not chunks:
            return f"文件 {file_id} 没有内容。"
        parts = [c.chunk_text for c in sorted(chunks, key=lambda x: x.chunk_index)]
        return "\n\n".join(parts)[:8000]

    return read_file
