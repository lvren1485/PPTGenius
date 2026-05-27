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
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

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
            items.append(f"[score={r['score']:.2f}] {r['text'][:500]}")
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


def _make_fetch_web(db: Database, user_id: int, conv_id: int):
    @tool
    async def fetch_web(url: str) -> str:
        """Fetch and index a web page. The page content will be added to the knowledge base.

        Use this after search_web to get the full content of a promising result.
        """
        result = await _web_search.fetch_and_ingest(db, url, user_id, conv_id)
        if result.get("ingested"):
            return (
                f"页面已抓取并索引。\n"
                f"标题: {result['title']}\n"
                f"域名: {result['domain']}\n"
                f"内容长度: {result['char_count']} 字符\n"
                f"内容预览:\n{result['text'][:2000]}"
            )
        return f"抓取失败或内容过短。标题: {result.get('title', 'N/A')}"

    return fetch_web


def _make_write_outline(db: Database, user_id: int, conv_id: int, initial_outline_id: int | None):
    """Returns (tool, get_ids).  Uses a mutable list wrapper so the tool can
    communicate outline_id and rationale back to the caller after create_agent
    completes."""
    _store: list[int | None] = [initial_outline_id]
    _rationale: list[str] = [""]

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
        return json.dumps({
            "outline_id": _store[0], "slide_count": len(slides),
            "design_rationale": design_rationale, "status": "ok",
        })

    def _get_ids() -> tuple[int | None, str]:
        return _store[0], _rationale[0]

    return write_outline, _get_ids


# ── helpers ──────────────────────────────────────────────────────────────────


def _extract_tool_result(messages: list, tool_name: str) -> dict | None:
    """Search messages in reverse for the first ToolMessage matching *tool_name*.

    create_agent's ToolMessages carry ``name`` matching the tool.
    """
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and getattr(msg, "name", None) == tool_name:
            try:
                return json.loads(str(msg.content))
            except (json.JSONDecodeError, TypeError):
                return None
    return None


# ── generator node ───────────────────────────────────────────────────────────


async def generator_node(state: OutlineState, config: RunnableConfig) -> dict:
    """Generator: build agent with create_agent, invoke, extract results."""
    db: Database = config["configurable"]["db"]
    user_id = state["user_id"]
    conv_id = state["conversation_id"]
    outline_id = state.get("outline_id")
    is_revision = outline_id is not None and state.get("evaluated", False)

    write_outline_tool, get_ids = _make_write_outline(db, user_id, conv_id, outline_id)
    tools = [
        _make_search_knowledge(user_id),
        _make_search_web(),
        _make_fetch_web(db, user_id, conv_id),
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

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config=config,
    )

    final_outline_id, rationale = get_ids()
    new_iteration = state.get("iteration", 0) + 1

    return {
        "outline_id": final_outline_id,
        "evaluated": False,
        "iteration": new_iteration,
        "design_rationale": rationale,
        "design_rationales": [rationale] if rationale else [],
        "messages": result["messages"],
    }
