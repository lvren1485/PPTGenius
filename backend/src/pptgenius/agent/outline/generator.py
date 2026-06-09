"""Outline content generator — fills content_json for existing slides only."""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.rag import KnowledgeService, WebSearchService
from pptgenius.infrastructure.utils import get_logger

from ..common.model_builder import build_llm
from .prompts import build_generator_system_prompt, build_generator_user_prompt

_log = get_logger("pptgenius.agent.outline.generator")

_web_search = WebSearchService()
_knowledge = KnowledgeService()

_FLAGS = ("待合并", "待分割", "待填充", "新页", "待修改")

# ── limits (from improvement.md §9) ──────────────────────────────────────────
_KB_SEARCH_LIMIT = 12
_WEB_SEARCH_LIMIT = 8
_FETCH_LIMIT = 6
_READ_LIMIT = 5


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


# ── chunk-id map (BM25 returns text only, cross-reference with DB) ────────────

async def _build_chunk_map(db: Database, user_id: int) -> dict[str, tuple[int, int]]:
    """Return {chunk_text: (chunk_id, file_id)} for all chunks owned by *user_id*."""
    chunks = await db.get_all_chunks_for_user(user_id)
    return {c.chunk_text: (c.id, c.file_id) for c in chunks}


# ── knowledge tools ───────────────────────────────────────────────────────────


def _make_search_knowledge(db: Database, user_id: int, count: list[int]):
    # Lazy-loaded chunk text → (chunk_id, file_id) map
    _chunk_map: dict[str, tuple[int, int]] | None = None

    async def _ensure_map():
        nonlocal _chunk_map
        if _chunk_map is None:
            _chunk_map = await _build_chunk_map(db, user_id)

    @tool
    async def search_knowledge(query: str, top_k: int = 5) -> str:
        """Search the user's personal knowledge base (BM25) for relevant documents.

        Use this first before searching the open web. Max 12 calls per round.
        Each result includes a chunk_id for citation.
        """
        if count[0] >= _KB_SEARCH_LIMIT:
            return f"搜索已达上限 ({_KB_SEARCH_LIMIT}次)。"
        count[0] += 1

        await _ensure_map()
        results = await _knowledge.search(user_id, query, top_k)
        if not results:
            return "知识库中未找到相关文档。"
        items = []
        for r in results:
            chunk_text = r.get("chunk", r.get("text", ""))
            cid, fid = _chunk_map.get(chunk_text, (None, None))
            items.append(
                f"[score={r.get('score', 0):.2f}] "
                f"chunk_id={cid} file_id={fid}\n"
                f"{chunk_text[:500]}"
            )
        return "\n\n---\n".join(items)

    return search_knowledge


def _make_search_web(count: list[int]):
    @tool
    async def search_web(query: str, max_results: int = 5) -> str:
        """Search the web for information. Returns title, URL, and snippet.

        Use this when the knowledge base doesn't have enough information.
        Max 8 calls per round.
        """
        if count[0] >= _WEB_SEARCH_LIMIT:
            return f"搜索已达上限 ({_WEB_SEARCH_LIMIT}次)。"
        count[0] += 1

        results = await _web_search.search(query, max_results)
        if not results:
            return "未找到相关网络结果。"
        items = []
        for i, r in enumerate(results):
            items.append(f"{i+1}. **{r['title']}**\n   URL: {r['url']}\n   {r['snippet']}")
        return "\n\n".join(items)

    return search_web


def _make_fetch_web(db: Database, user_id: int, conv_id: int, count: list[int]):
    @tool
    async def fetch_web(url: str) -> str:
        """Fetch and index a web page. The content is added to the knowledge base.

        Use after search_web to read a promising result. Max 6 fetches per round.
        """
        if count[0] >= _FETCH_LIMIT:
            return f"抓取已达上限 ({_FETCH_LIMIT}次)。"
        count[0] += 1
        result = await _web_search.fetch_and_ingest(db, url, user_id, conv_id)
        if result.get("ingested"):
            return f"已抓取: {result['title']}\n{result['text'][:1000]}\n详细内容已加入知识库。"
        return f"抓取失败。{result.get('title', 'N/A')}"

    return fetch_web


def _make_read_file(db: Database, count: list[int], fetched_ids: set[int]):
    @tool
    async def read_file(file_id: int) -> str:
        """Read full content of a knowledge file. Max 5 per round."""
        if count[0] >= _READ_LIMIT:
            return f"读取已达上限 ({_READ_LIMIT}次)。"
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


# ── write tool (overwrite only, no create/delete) ─────────────────────────────


def _make_write_slides(db: Database, outline_id: int, section_id: int):
    _called: list[bool] = [False]

    @tool
    async def write_slides(
        slides: list[dict],
        citations: list[dict] | None = None,
    ) -> str:
        """Overwrite content for existing section slides. MUST be called last.

        Only fills content_json / has_image / has_chart / notes on pre-created
        slides. Does NOT create or delete slides. Target slides by slide_index.

        Parameters
        ----------
        slides : list[dict] — [{slide_index, content_json, has_image, has_chart, notes}, ...]
        citations : list[dict] | None — [{chunk_id, reason}, ...], cite knowledge sources used.
        """
        existing = await db.get_slides_by_outline_id(outline_id)
        sec_slides = sorted(
            [s for s in existing if s.section_id == section_id],
            key=lambda s: s.slide_index,
        )
        index_map = {s.slide_index: s for s in sec_slides}

        # Resolve chunk_id → file_id for citations
        resolved_citations: list[dict] | None = None
        if citations:
            resolved_citations = []
            for c in citations:
                cid = c.get("chunk_id")
                if cid is None:
                    continue
                chunk = await db.get_chunk_by_id(cid)
                fid = chunk.file_id if chunk else None
                resolved_citations.append({
                    "chunk_id": cid,
                    "knowledge_file_id": fid,
                    "reason": c.get("reason", ""),
                })

        updated = 0
        for sl in slides:
            si = sl.get("slide_index")
            target = index_map.get(si)
            if target is None:
                continue
            updates: dict = {"status": "completed"}
            if "content_json" in sl:
                updates["content_json"] = sl["content_json"]
            if "has_image" in sl:
                updates["has_image"] = sl["has_image"]
            if "has_chart" in sl:
                updates["has_chart"] = sl["has_chart"]
            if "notes" in sl:
                updates["notes"] = sl["notes"]
            await db.update_outline_slide(target.id, **updates)
            if resolved_citations:
                await db.update_outline_slide_citations(target.id, resolved_citations)
            updated += 1

        _called[0] = True
        return json.dumps({"section_id": section_id, "updated": updated,
                           "citations": len(resolved_citations) if resolved_citations else 0,
                           "status": "ok"})

    return write_slides, _called


# ── main entry ────────────────────────────────────────────────────────────────


async def run_outline_generator(
    db: Database,
    conversation_id: int,
    section_id: int,
    *,
    query: str | None = None,
    knowledge_mode: str = "auto",
) -> str:
    """Fill content for one section's pre-created slides."""
    writer = _get_writer()

    section = await db.get_outline_section(section_id)
    if section is None:
        return f"错误: section {section_id} 不存在"

    outline = await db.get_outline(section.outline_id)
    conv = await db.get_conversation(conversation_id)
    user_id = conv.user_id if conv else 0

    kb_count = [0]
    web_count = [0]
    fetch_count = [0]
    read_count = [0]
    fetched_ids: set[int] = set()

    write_tool, was_called = _make_write_slides(db, section.outline_id, section_id)
    tools = [
        _make_search_knowledge(db, user_id, kb_count),
        _make_search_web(web_count),
        _make_fetch_web(db, user_id, conversation_id, fetch_count),
        _make_read_file(db, read_count, fetched_ids),
        write_tool,
    ]

    system_prompt = build_generator_system_prompt()
    user_prompt = await build_generator_user_prompt(
        db=db,
        outline_id=section.outline_id,
        section_id=section_id,
        query=query,
        knowledge_mode=knowledge_mode,
    )

    llm, agent_id, mw = build_llm(conversation_id)
    agent = create_agent(
        model=llm, tools=tools,
        system_prompt=system_prompt,
        middleware=[mw],
    )

    writer({"type": "outline_generator_start", "section": section.title})
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config={"recursion_limit": 30},
    )

    if not was_called[0]:
        _log.warning("write_slides not called — retrying")
        retry_msg = HumanMessage(content="请立即调用 write_slides 工具写入内容。不要再搜索或分析，直接写入。")
        clean = _strip_dangling_tool_calls(result["messages"])
        await agent.ainvoke(
            {"messages": clean + [retry_msg]},
            config={"recursion_limit": 30},
        )

    writer({"type": "outline_generator_end", "section": section.title})
    return f"章节'{section.title}'填充完成"


def _strip_dangling_tool_calls(messages: list) -> list:
    cleaned = list(messages)
    while cleaned and isinstance(cleaned[-1], AIMessage) and cleaned[-1].tool_calls:
        cleaned.pop()
    return cleaned
