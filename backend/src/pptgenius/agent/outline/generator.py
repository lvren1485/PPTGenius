"""Generator agent — uses LangChain create_agent for the ReAct tool-calling loop.

The generator has four tools:
- ``search_knowledge`` — BM25 search across the user's knowledge base
- ``search_web`` — web search via DuckDuckGo / SearXNG
- ``fetch_web`` — fetch + index a single URL
- ``write_outline`` — persist the outline + slides to DB (terminal tool)

create_agent handles the ReAct loop (model → tools → model → ...)
and manages DeepSeek reasoning_content natively.
"""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.rag import KnowledgeService, WebSearchService
from pptgenius.infrastructure.utils import get_logger

from .middleware import TokenCountingMiddleware
from .prompts import build_generator_user_prompt, load_generator_system
from .state import OutlineState

_log = get_logger("pptgenius.agent.outline.generator")

_web_search = WebSearchService()
_knowledge = KnowledgeService()

apply_deepseek_patch()


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )


# ── tools (built as closures so they capture db / state at runtime) ──


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
        """Search the web for information. Returns title, URL, and snippet for each result.

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


def _make_list_files(db: Database, user_id: int):
    @tool
    async def list_knowledge_files(dummy: str = "") -> str:
        """List all knowledge files belonging to the current user.
        Pass an empty string as the argument.
        """
        files = await db.list_knowledge_files(user_id)
        if not files:
            return "知识库中没有任何文件。"
        items = []
        for f in files[:50]:
            items.append(f"- [{f.file_type}] {f.filename} ({f.chunk_count} chunks, {f.file_size} bytes)")
        return "\n".join(items)

    return list_knowledge_files


def _make_read_file(db: Database, fetch_count: list[int], fetched_ids: set[int]):
    @tool
    async def read_file(file_id: int) -> str:
        """Read the full text of a knowledge file (all chunks). Use this after
        list_knowledge_files to get the complete content of a relevant file.

        Parameters
        ----------
        file_id : int — The file ID from list_knowledge_files.
        """
        if fetch_count[0] >= 4:
            return f"本轮抓取已达上限 (4次)。请基于已有信息生成大纲。"
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
        full = "\n\n".join(parts)
        return full[:8000]

    return read_file


def _make_list_input_images(conv_id: int):
    @tool
    async def list_input_images(dummy: str = "") -> str:
        """List all image files available in this conversation's input directory.

        These are images uploaded by the user that can be referenced in the PPT.
        Pass an empty string as the argument.
        """
        from pathlib import Path
        from pptgenius.infrastructure.config import get_settings

        cfg = get_settings().workspace
        input_dir = Path(cfg.root) / str(conv_id) / cfg.input_dir
        if not input_dir.exists():
            return "没有上传的图片素材。"

        image_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
        images = []
        for f in sorted(input_dir.iterdir()):
            if f.suffix.lower() in image_suffixes:
                size_kb = f.stat().st_size / 1024
                images.append(f"- {f.name} ({size_kb:.1f} KB)")

        if not images:
            return "没有上传的图片素材。"

        return "可用图片素材:\n" + "\n".join(images)

    return list_input_images


def _make_fetch_web(db: Database, user_id: int, conv_id: int, fetch_count: list[int]):
    @tool
    async def fetch_web(url: str) -> str:
        """Fetch and index a web page. The page content will be added to the knowledge base.

        Use this after search_web to get the full content of a promising result.
        """
        if fetch_count[0] >= 4:
            return f"本轮抓取已达上限 (4次)。请基于已有信息生成大纲。"
        fetch_count[0] += 1
        result = await _web_search.fetch_and_ingest(db, url, user_id, conv_id)
        if result.get("ingested"):
            return (
                f"页面已抓取并索引。\n"
                f"标题: {result['title']}\n"
                f"域名: {result['domain']}\n"
                f"内容长度: {result['char_count']} 字符\n"
                f"内容预览:\n{result['text'][:1000]}"
            )
        return f"抓取失败或内容过短。标题: {result.get('title', 'N/A')}"

    return fetch_web


def _make_write_outline(db: Database, user_id: int, conv_id: int, initial_outline_id: int | None):
    """Returns (tool, get_ids, was_called).  Uses mutable list wrappers to
    communicate outline_id, rationale, and whether the tool was invoked."""
    _store: list[int | None] = [initial_outline_id]
    _rationale: list[str] = [""]
    _called: list[bool] = [False]

    @tool
    async def write_outline(
        title: str,
        design_rationale: str,
        slides: list[dict],
    ) -> str:
        """Write (create or replace) the outline and all its slides to the database.

        This is the FINAL action — call this after researching and designing.

        Parameters
        ----------
        title : str — The outline title.
        design_rationale : str — Your design rationale: narrative thread, tradeoffs.
        slides : list[dict] — Each slide:
            {slide_index, title, content_json, layout_type, has_image, has_chart, notes}
            content_json MUST include: main_points, detailed_content, key_data,
            visual_note, recommended_ppt_format (one of: bullet_list, two_column,
            flowchart, chart, image_full, text_with_image, timeline, comparison,
            table, big_number, quote, diagram, three_column, four_grid)
        """
        if _store[0] is None:
            outline = await db.create_outline(
                user_id=user_id, conversation_id=conv_id,
                title=title, slide_count=len(slides),
            )
            _store[0] = outline.id
            _log.info("created outline id=%d with %d slides", outline.id, len(slides))
        else:
            await db.increment_outline_version(_store[0])
            _log.info("revising outline id=%d (new version)", _store[0])

        await db.replace_outline_slides(_store[0], slides)
        _rationale[0] = design_rationale
        _called[0] = True
        return json.dumps({
            "outline_id": _store[0], "slide_count": len(slides),
            "design_rationale": design_rationale, "status": "ok",
        })

    def _get_result() -> tuple[int | None, str, bool]:
        return _store[0], _rationale[0], _called[0]

    return write_outline, _get_result



# ── generator node ───────────────────────────────────────────────────────────


async def generator_node(state: OutlineState, config: RunnableConfig) -> dict:
    """Generator: build agent with create_agent, invoke, extract results."""
    db: Database = config["configurable"]["db"]
    user_id = state["user_id"]
    conv_id = state["conversation_id"]
    outline_id = state.get("outline_id")
    is_revision = outline_id is not None and state.get("evaluated", False)
    try:
        writer = get_stream_writer()
    except RuntimeError:
        writer = lambda _: None  # no-op when not inside a running graph (e.g. tests)

    # Per-round fetch tracking (fetch_web, max 4 per round)
    fetch_count = [0]

    write_outline_tool, get_result = _make_write_outline(db, user_id, conv_id, outline_id)
    tools = [
        _make_list_input_images(conv_id),
        _make_search_knowledge(user_id),
        _make_search_web(),
        _make_fetch_web(db, user_id, conv_id, fetch_count),
        write_outline_tool,
    ]

    previous_rationales = state.get("design_rationales", [])
    system_prompt = load_generator_system()
    user_prompt = build_generator_user_prompt(
        query=state["query"],
        design_rationale="\n---\n".join(previous_rationales) if previous_rationales else "",
        eval_suggestions=state.get("eval_suggestions", ""),
        is_revision=is_revision,
    )

    agent = create_agent(
        model=_get_model(),
        tools=tools,
        system_prompt=system_prompt,
        middleware=[TokenCountingMiddleware(conv_id)],
    )

    writer({"type": "generator_start", "is_revision": is_revision})
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config=config,
    )
    writer({"type": "generator_end", "was_called": False})  # placeholder

    final_outline_id, rationale, was_called = get_result()
    new_iteration = state.get("iteration", 0) + 1

    # If write_outline wasn't called, retry once with an explicit instruction.
    # Strip dangling tool_calls (AIMessage with tool_calls but no matching
    # ToolMessage) — DeepSeek rejects these with 400.
    if not was_called:
        _log.warning("write_outline not called — retrying with explicit instruction")
        retry_msg = HumanMessage(content="请立即调用 write_outline 工具保存大纲。不要再搜索或分析，直接保存。")
        clean_msgs = _strip_dangling_tool_calls(result["messages"])
        result2 = await agent.ainvoke(
            {"messages": clean_msgs + [retry_msg]},
            config=config,
        )
        final_outline_id, rationale, was_called = get_result()
        result = result2

    return {
        "outline_id": final_outline_id,
        "evaluated": False,
        "iteration": new_iteration,
        "design_rationale": rationale,
        "design_rationales": [rationale] if rationale else [],
        "messages": result["messages"],
    }


def _strip_dangling_tool_calls(messages: list) -> list:
    """Remove trailing AIMessages with tool_calls that lack matching ToolMessages.

    DeepSeek rejects message histories where an assistant message has tool_calls
    but no subsequent ToolMessage responses (400 insufficient tool messages).
    """
    cleaned = list(messages)
    while cleaned and isinstance(cleaned[-1], AIMessage) and cleaned[-1].tool_calls:
        cleaned.pop()
    return cleaned
