"""Generator node — LLM agent that creates/revises PPT outlines.

The generator has four tools:
- ``search_knowledge`` — BM25 search across the user's knowledge base
- ``search_web`` — web search via DuckDuckGo / SearXNG
- ``fetch_web`` — fetch + index a single URL
- ``write_outline`` — persist the outline + slides to DB (terminal tool)

After the LLM calls ``write_outline`` the node returns updated state.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.rag import KnowledgeService, WebSearchService
from pptgenius.infrastructure.utils import get_logger

from .prompts import (
    build_generator_user_prompt,
    load_generator_system,
)
from .state import OutlineState

_log = get_logger("pptgenius.agent.outline.generator")

_web_search = WebSearchService()
_knowledge = KnowledgeService()


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )


# ── tools (built as closures inside the node so they capture db / state) ──


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


def _make_write_outline(db: Database, user_id: int, conv_id: int, outline_id: int | None):
    @tool
    async def write_outline(
        title: str,
        design_rationale: str,
        slides: list[dict],
    ) -> str:
        """Write (create or replace) the outline and all its slides to the database.

        This is the FINAL action — call this after you've finished researching and designing.

        Parameters
        ----------
        title : str
            The outline title.
        design_rationale : str
            Your design rationale: why this structure, narrative thread, tradeoffs made.
        slides : list[dict]
            Each slide: {slide_index, title, content_json, layout_type, has_image, has_chart, notes}
            - slide_index: 0-based index
            - layout_type: title | content | section | summary | thanks
            - content_json: {main_points, detailed_content, key_data, visual_note}
        """
        nonlocal outline_id

        if outline_id is None:
            outline = await db.create_outline(
                user_id=user_id,
                conversation_id=conv_id,
                title=title,
                slide_count=len(slides),
            )
            outline_id = outline.id
            _log.info("created outline id=%d with %d slides", outline_id, len(slides))
        else:
            await db.increment_outline_version(outline_id)
            _log.info("revising outline id=%d (new version)", outline_id)

        await db.replace_outline_slides(outline_id, slides)
        return json.dumps({"outline_id": outline_id, "slide_count": len(slides), "status": "ok"})

    return write_outline


# ── generator node ──────────────────────────────────────────────────────────


async def generator_node(state: OutlineState, config: RunnableConfig) -> dict:
    """Generator agent: research → design → write_outline.

    Runs a tool-calling loop until ``write_outline`` is called (or max turns
    exceeded).
    """
    db: Database = config["configurable"]["db"]
    user_id = state["user_id"]
    conv_id = state["conversation_id"]
    outline_id = state.get("outline_id")
    is_revision = outline_id is not None and state.get("evaluated", False)

    model = _get_model()

    tools = [
        _make_search_knowledge(user_id),
        _make_search_web(),
        _make_fetch_web(db, user_id, conv_id),
        _make_write_outline(db, user_id, conv_id, outline_id),
    ]
    tools_by_name = {t.name: t for t in tools}
    model_with_tools = model.bind_tools(tools)

    system_prompt = load_generator_system()
    user_prompt = build_generator_user_prompt(
        query=state["query"],
        design_rationale=state.get("design_rationale", ""),
        eval_suggestions=state.get("eval_suggestions", ""),
        is_revision=is_revision,
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    final_outline_id: int | None = None
    max_turns = 20

    for _turn in range(max_turns):
        response = await model_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            _log.warning("generator stopped without calling write_outline")
            break

        for tc in response.tool_calls:
            tool_func = tools_by_name.get(tc["name"])
            if tool_func is None:
                messages.append(ToolMessage(
                    content=f"Unknown tool: {tc['name']}", tool_call_id=tc["id"]
                ))
                continue

            try:
                result = await tool_func.ainvoke(tc["args"])
            except Exception as exc:
                _log.exception("tool %s failed", tc["name"])
                result = f"Tool error: {exc}"

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

            if tc["name"] == "write_outline":
                parsed = json.loads(str(result))
                final_outline_id = parsed["outline_id"]
                break

        if final_outline_id is not None:
            break
    else:
        _log.error("generator exceeded max turns (%d)", max_turns)

    new_iteration = state.get("iteration", 0) + 1

    return {
        "outline_id": final_outline_id,
        "evaluated": False,
        "iteration": new_iteration,
        "messages": messages,
    }
