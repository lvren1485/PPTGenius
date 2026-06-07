"""Outline content generator sub-agent — ReAct agent for generating slide content."""

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
from .prompts import build_generator_system_prompt

_log = get_logger("pptgenius.agent.outline.generator")

_web_search = WebSearchService()
_knowledge = KnowledgeService()


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


# ── tool factories (capture db / state at runtime via closure) ────────────────


def _make_search_knowledge(user_id: int):
    @tool
    async def search_knowledge(query: str, top_k: int = 5) -> str:
        """Search the user's personal knowledge base (BM25) for relevant documents.

        Use this first before searching the open web.
        """
        results = await _knowledge.search(user_id, query, top_k)
        if not results:
            return "知识库中未找到相关文档。"
        items = []
        for r in results:
            chunk_text = r.get("chunk", r.get("text", ""))
            items.append(f"[score={r.get('score', 0):.2f}] {chunk_text[:500]}")
        return "\n\n---\n".join(items)

    return search_knowledge


def _make_search_web():
    @tool
    async def search_web(query: str, max_results: int = 5) -> str:
        """Search the web for information. Returns title, URL, and snippet.

        Use this when the knowledge base doesn't have enough information.
        """
        results = await _web_search.search(query, max_results)
        if not results:
            return "未找到相关网络结果。"
        items = []
        for i, r in enumerate(results):
            items.append(f"{i+1}. **{r['title']}**\n   URL: {r['url']}\n   {r['snippet']}")
        return "\n\n".join(items)

    return search_web


def _make_fetch_web(db: Database, user_id: int, conv_id: int, fetch_count: list[int]):
    @tool
    async def fetch_web(url: str) -> str:
        """Fetch and index a web page. The content is added to the knowledge base.

        Use after search_web to read a promising result. Max 4 fetches per round.
        """
        if fetch_count[0] >= 4:
            return "本轮抓取已达上限 (4次)。请基于已有信息生成内容。"
        fetch_count[0] += 1
        result = await _web_search.fetch_and_ingest(db, url, user_id, conv_id)
        if result.get("ingested"):
            return (
                f"页面已抓取并索引。\n"
                f"标题: {result['title']}\n域名: {result['domain']}\n"
                f"内容长度: {result['char_count']} 字符\n"
                f"内容预览:\n{result['text'][:1000]}"
            )
        return f"抓取失败。标题: {result.get('title', 'N/A')}"

    return fetch_web


def _make_read_file(db: Database, fetch_count: list[int], fetched_ids: set[int]):
    @tool
    async def read_file(file_id: int) -> str:
        """Read the full content of a knowledge file by id. Max 4 reads per round.

        Use after list_knowledge_files to get complete content of a relevant file.
        """
        if fetch_count[0] >= 4:
            return "本轮读取已达上限 (4次)。请基于已有信息生成内容。"
        if file_id in fetched_ids:
            return f"already fetched (file_id={file_id})"
        fetch_count[0] += 1
        fetched_ids.add(file_id)
        chunks = await db.list_chunks_by_file(file_id)
        if not chunks:
            return f"文件 {file_id} 没有内容。"
        parts = []
        for c in sorted(chunks, key=lambda x: x.chunk_index):
            parts.append(c.chunk_text)
        return "\n\n".join(parts)[:8000]

    return read_file


def _make_write_outline_slides(db: Database, outline_id: int, section_id: int):
    """Returns (tool, was_called).  write_outline_slides persists slides for one section."""
    _called: list[bool] = [False]

    @tool
    async def write_outline_slides(
        design_rationale: str,
        slides: list[dict],
    ) -> str:
        """Write generated slides for this section to the database. MUST be called last.

        Parameters
        ----------
        design_rationale : str — Design rationale for this section's content.
        slides : list[dict] — Each slide:
            {title, content_json, layout_type, has_image, has_chart, notes}
            content_json MUST include: main_points, detailed_content, key_data,
            visual_note, recommended_ppt_format.
        """
        await db.replace_section_slides(outline_id, section_id, slides)
        _called[0] = True
        return json.dumps({"section_id": section_id, "slide_count": len(slides), "status": "ok"})

    return write_outline_slides, _called


# ── main entry ─────────────────────────────────────────────────────────────────


async def run_outline_generator(
    db: Database,
    conversation_id: int,
    section_id: int,
    *,
    query: str | None = None,
    knowledge_mode: str = "auto",
    regenerate_slides: list[int] | None = None,
) -> str:
    """Run the outline content generator ReAct agent for one section."""
    writer = _get_writer()

    section = await db.get_outline_section(section_id)
    if section is None:
        return f"错误: section {section_id} 不存在"

    outline = await db.get_outline(section.outline_id)
    conv = await db.get_conversation(conversation_id)
    user_id = conv.user_id if conv else 0

    fetch_count = [0]
    fetched_ids: set[int] = set()

    write_tool, was_called = _make_write_outline_slides(db, section.outline_id, section_id)
    tools = [
        _make_search_knowledge(user_id),
        _make_search_web(),
        _make_fetch_web(db, user_id, conversation_id, fetch_count),
        _make_read_file(db, fetch_count, fetched_ids),
        write_tool,
    ]

    system_prompt = build_generator_system_prompt()
    is_regenerate = bool(regenerate_slides)
    user_prompt = _build_user_prompt(
        section.title or "",
        section.description or "",
        query,
        is_regenerate,
    )

    llm, agent_id, mw = build_llm(conversation_id)
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[mw],
    )

    writer({"type": "outline_generator_start", "section": section.title,
            "is_regenerate": is_regenerate})
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config={"recursion_limit": 30},
    )

    if not was_called[0]:
        _log.warning("write_outline_slides not called — retrying")
        retry_msg = HumanMessage(content="请立即调用 write_outline_slides 工具保存内容。不要再搜索或分析，直接保存。")
        clean_msgs = _strip_dangling_tool_calls(result["messages"])
        await agent.ainvoke(
            {"messages": clean_msgs + [retry_msg]},
            config={"recursion_limit": 30},
        )

    writer({"type": "outline_generator_end", "section": section.title})
    return f"章节'{section.title}'生成完成"


def _build_user_prompt(
    section_title: str,
    section_description: str,
    query: str | None,
    is_regenerate: bool,
) -> str:
    parts = [f"## 章节: {section_title}"]
    if section_description:
        parts.append(f"描述: {section_description}")
    if query:
        parts.append(f"用户要求: {query}")
    if is_regenerate:
        parts.append("注意: 这是**修改已有内容**。只重新生成需要修改的页面，保留其他页面不变。")
    else:
        parts.append("请根据章节主题设计该章节的幻灯片内容，使用 write_outline_slides 保存。")
    return "\n".join(parts)


def _strip_dangling_tool_calls(messages: list) -> list:
    """Remove trailing AIMessages with tool_calls lacking matching ToolMessages."""
    cleaned = list(messages)
    while cleaned and isinstance(cleaned[-1], AIMessage) and cleaned[-1].tool_calls:
        cleaned.pop()
    return cleaned
