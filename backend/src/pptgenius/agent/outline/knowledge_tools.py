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

# Suffix appended to every tool result to nudge the model toward write_slides
_WRITE_HINT = "\n\n 如果已收集到足够信息，请立即调用 write_slides 工具写入内容。禁止直接输出"


async def _build_chunk_map(
    db: Database,
    user_id: int,
    conversation_id: int,
    rag_mode: str,
) -> dict[str, tuple[int, int]]:
    """Return {chunk_text[:20]: (chunk_id, file_id)} for the active scope."""
    if rag_mode == "conversation":
        chunks = await db.get_all_chunks_for_conversation(conversation_id)
    else:
        chunks = await db.get_all_chunks_for_user(user_id)
    return {c.chunk_text[:20]: (c.id, c.file_id) for c in chunks}


def make_search_knowledge(
    db: Database,
    user_id: int,
    conversation_id: int,
    rag_mode: str,
    count: list[int],
):
    _chunk_map: dict[str, tuple[int, int]] | None = None

    async def _ensure_map():
        nonlocal _chunk_map
        if _chunk_map is None:
            _chunk_map = await _build_chunk_map(db, user_id, conversation_id, rag_mode)

    @tool
    async def search_knowledge(query: str, top_k: int = 5) -> str:
        """Search the user's personal knowledge base (BM25) for relevant documents.

        Use this first before searching the open web. Max 9 calls per round.
        Each result includes a chunk_id for citation.
        """
        if count[0] >= _KB_SEARCH_LIMIT:
            return f"搜索已达上限 ({_KB_SEARCH_LIMIT}次)。请立即调用 write_slides 工具写入内容。禁止直接输出。"
        count[0] += 1

        await _ensure_map()

        if rag_mode == "conversation":
            results = await _knowledge.search_by_conversation(
                db, conversation_id, query, top_k,
            )
        else:
            results = await _knowledge.search(user_id, query, top_k)

        if not results:
            return "知识库中未找到相关文档。" + _WRITE_HINT
        items = []
        for r in results:
            chunk_text = r.get("chunk", r.get("text", ""))
            cid, fid = _chunk_map.get(chunk_text[:20], (None, None))
            items.append(
                f"[score={r.get('score', 0):.2f}] "
                f"chunk_id={cid} file_id={fid}\n"
                f"{chunk_text[:500]}"
            )
        return "\n\n---\n".join(items) + _WRITE_HINT

    return search_knowledge


def make_search_web(count: list[int]):
    @tool
    async def search_web(query: str, max_results: int = 5) -> str:
        """Search the web for information. Returns title, URL, and snippet.

        Use this when the knowledge base doesn't have enough information.
        Max 6 calls per round.
        """
        if count[0] >= _WEB_SEARCH_LIMIT:
            return f"搜索已达上限 ({_WEB_SEARCH_LIMIT}次)。请立即调用 write_slides 工具写入内容。禁止直接输出。"
        count[0] += 1

        try:
            results = await _web_search.search(query, max_results)
        except Exception as e:
            _log.warning("web search failed: %s", e)
            return f"网络搜索失败: {e}。可尝试换关键词或直接使用知识库内容。" + _WRITE_HINT
        if not results:
            return "未找到相关网络结果。" + _WRITE_HINT
        items = []
        for i, r in enumerate(results):
            items.append(f"{i+1}. **{r['title']}**\n   URL: {r['url']}\n   {r['snippet']}")
        return "\n\n".join(items) + _WRITE_HINT

    return search_web


def make_fetch_web(db: Database, user_id: int, conv_id: int, count: list[int]):
    @tool
    async def fetch_web(url: str) -> str:
        """Fetch and index a web page. The content is added to the knowledge base.

        Use after search_web to read a promising result. Max 4 fetches per round.
        """
        if count[0] >= _FETCH_LIMIT:
            return f"抓取已达上限 ({_FETCH_LIMIT}次)。请立即调用 write_slides 写入内容。禁止直接输出。"
        count[0] += 1
        try:
            result = await _web_search.fetch_and_ingest(db, url, user_id, conv_id)
        except Exception as e:
            _log.warning("web fetch failed: %s — %s", url, e)
            return f"网页抓取失败: {e}。请尝试其他搜索结果。" + _WRITE_HINT
        if result.get("ingested"):
            file_id = result.get("knowledge_file_id")
            if file_id:
                await db.set_knowledge_file_web_url(file_id, url)
            return f"已抓取: {result['title']}\n{result['text'][:1000]}\n详细内容已加入知识库。" + _WRITE_HINT
        return f"抓取失败。{result.get('title', 'N/A')}" + _WRITE_HINT

    return fetch_web


def make_read_file(db: Database, count: list[int], fetched_ids: set[int]):
    @tool
    async def read_file(file_id: int) -> str:
        """Read full content of a knowledge file. Max 3 per round."""
        if count[0] >= _READ_LIMIT:
            return f"读取已达上限 ({_READ_LIMIT}次)。请立即调用 write_slides 工具写入内容。禁止直接输出。"
        if file_id in fetched_ids:
            return f"already fetched (file_id={file_id})"
        count[0] += 1
        fetched_ids.add(file_id)
        chunks = await db.list_chunks_by_file(file_id)
        if not chunks:
            return f"文件 {file_id} 没有内容。"
        parts = [c.chunk_text for c in sorted(chunks, key=lambda x: x.chunk_index)]
        return "\n\n".join(parts)[:8000] + _WRITE_HINT

    return read_file
