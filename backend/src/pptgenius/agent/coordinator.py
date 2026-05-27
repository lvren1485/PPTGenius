"""Coordinator agent — intent classification + sub-agent dispatch.

Analyses the user message and current conversation state, then routes to:
- outline agent (generate / modify)
- PPT agent (generate / modify — placeholder)
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.agent.outline import build_outline_graph, OutlineState
from pptgenius.agent.ppt import build_ppt_graph
from pptgenius.infrastructure.config import RESOURCES_DIR, get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

apply_deepseek_patch()

_log = get_logger("pptgenius.agent.coordinator")

_PROMPT_PATH = RESOURCES_DIR / "prompts" / "coordinator_system.txt"


# ── structured output model ──────────────────────────────────────────────────


class CoordinatorDecision(BaseModel):
    task: Literal[
        "generate_outline",
        "modify_outline",
        "generate_ppt",
        "modify_ppt",
    ] = Field(description="The task type to execute")
    reasoning: str = Field(description="Brief reasoning for this decision")


# ── helpers ──────────────────────────────────────────────────────────────────


def _get_model():
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        temperature=0.1,
        max_tokens=2000,
    )


def _load_coordinator_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    _log.warning("coordinator prompt not found at %s, using default", _PROMPT_PATH)
    return "You are a PPT assistant coordinator. Classify the user intent."


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── intent classification ────────────────────────────────────────────────────


async def _classify_intent(
    query: str,
    has_outline: bool,
    has_ppt: bool,
    outline_title: str = "",
    history_summary: str = "",
) -> CoordinatorDecision:
    """Use LLM to classify the user's intent into one of 4 task types."""
    model = _get_model()
    structured_model = model.with_structured_output(CoordinatorDecision)

    system = _load_coordinator_prompt()

    state_lines = [
        "## 当前状态",
        f"- 大纲是否存在: {'是' if has_outline else '否'}",
        f"- PPT是否存在: {'是' if has_ppt else '否'}",
    ]
    if has_outline and outline_title:
        state_lines.append(f"- 当前大纲标题: {outline_title}")
    if history_summary:
        state_lines.append(f"\n## 最近对话历史\n{history_summary}")

    state_lines.append(f"\n## 用户最新消息\n{query}")

    user_msg = "\n".join(state_lines)

    result = await structured_model.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=user_msg),
    ])
    _log.info("coordinator decision: %s (reason: %s)", result.task, result.reasoning)
    return result


# ── main entry point ─────────────────────────────────────────────────────────


async def run_coordinator(
    db: Database,
    conversation_id: int,
    query: str,
) -> AsyncGenerator[str, None]:
    """Analyse user intent and dispatch to the appropriate sub-agent.

    Yields SSE-formatted strings for the chat endpoint.
    """
    conv = await db.get_conversation(conversation_id)
    if conv is None:
        yield _sse("error", {"code": 40001, "message": "conversation not found", "retryable": False})
        return

    user_id = conv.user_id
    cfg = get_settings().agent.outline

    # --- load current state ---
    outlines = await db.list_outlines_by_conversation(conversation_id)
    presentations = await db.list_presentations_by_conversation(conversation_id)
    latest_outline = outlines[0] if outlines else None
    latest_ppt = presentations[0] if presentations else None

    # --- classify intent ---
    decision = await _classify_intent(
        query=query,
        has_outline=latest_outline is not None,
        has_ppt=latest_ppt is not None,
        outline_title=latest_outline.title if latest_outline else "",
    )

    yield _sse("phase", {"phase": decision.task, "message": f"协调Agent判断: {decision.task}"})

    # --- dispatch ---
    if decision.task in ("generate_outline", "modify_outline"):
        async for event in _run_outline(
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            existing_outline=latest_outline if decision.task == "modify_outline" else None,
            cfg=cfg,
        ):
            yield event

    elif decision.task in ("generate_ppt", "modify_ppt"):
        async for event in _run_ppt(
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            outline=latest_outline,
            existing_ppt=latest_ppt,
        ):
            yield event


# ── outline sub-agent runner ─────────────────────────────────────────────────


async def _run_outline(
    db: Database,
    user_id: int,
    conversation_id: int,
    query: str,
    existing_outline,
    cfg,
) -> AsyncGenerator[str, None]:
    """Run the outline generator-evaluator graph."""
    is_modify = existing_outline is not None

    state: OutlineState = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "query": query,
        "outline_id": existing_outline.id if existing_outline else None,
        "evaluated": is_modify,  # True → generator (revision), False → evaluator first for new
        "iteration": 0,
        "eval_score": existing_outline.eval_score if existing_outline else None,
        "eval_suggestions": "",
        "mode": cfg.mode,
        "max_iterations": cfg.max_iterations,
        "pass_score": cfg.pass_score,
        "design_rationale": "",
        "messages": [],
    }

    graph = build_outline_graph()

    if is_modify:
        yield _sse("phase", {"phase": "outline", "message": "开始修改大纲..."})
    else:
        yield _sse("phase", {"phase": "outline", "message": "开始生成大纲..."})

    try:
        async for event in graph.astream_events(state, config={"configurable": {"db": db}}, version="v2"):
            kind = event["event"]

            if kind == "on_tool_start":
                async for sse in _tool_start_sse(event):
                    yield sse

            elif kind == "on_tool_end":
                async for sse in _tool_end_sse(event, db):
                    yield sse

    except Exception:
        _log.exception("outline agent error")
        yield _sse("error", {"code": 40200, "message": "大纲生成失败", "retryable": True})
        return

    # Emit final outline state
    async for sse in _emit_final_outline(db, conversation_id):
        yield sse


# ── PPT sub-agent runner (placeholder) ───────────────────────────────────────


async def _run_ppt(
    db: Database,
    user_id: int,
    conversation_id: int,
    query: str,
    outline,
    existing_ppt,
) -> AsyncGenerator[str, None]:
    """Run the PPT agent (placeholder)."""
    if outline is None:
        yield _sse("error", {"code": 40301, "message": "请先生成大纲再生成PPT", "retryable": False})
        return

    _log.warning("PPT agent not implemented — outline_id=%d", outline.id)
    yield _sse("phase", {"phase": "ppt", "message": "PPT生成功能开发中..."})
    yield _sse("progress", {"step": "pending", "detail": "PPT agent not yet implemented", "pct": 0})


# ── SSE event helpers ────────────────────────────────────────────────────────


async def _tool_start_sse(event: dict):
    name = event["name"]
    if name == "search_knowledge":
        yield _sse("progress", {"step": "searching_knowledge", "detail": "检索知识库...", "pct": 10})
    elif name == "search_web":
        yield _sse("progress", {"step": "searching_web", "detail": "搜索网络...", "pct": 20})
    elif name == "fetch_web":
        yield _sse("progress", {"step": "fetching_web", "detail": "获取网页内容...", "pct": 30})
    elif name == "write_outline":
        yield _sse("progress", {"step": "writing_outline", "detail": "正在生成大纲...", "pct": 50})
    elif name == "submit_evaluation":
        yield _sse("progress", {"step": "evaluating", "detail": "评估中...", "pct": 70})


async def _tool_end_sse(event: dict, db: Database):
    name = event["name"]
    output = event["data"].get("output")

    if name == "write_outline" and output:
        try:
            result = json.loads(str(output))
            outline_id = result.get("outline_id")
            if outline_id:
                outline = await db.get_outline(outline_id)
                slides = await db.get_slides_by_outline_id(outline_id)
                if outline:
                    yield _sse("outline", {
                        "outline_id": outline.id,
                        "title": outline.title,
                        "version": outline.version,
                        "slide_count": outline.slide_count,
                        "slides": [
                            {
                                "slide_index": s.slide_index,
                                "title": s.title,
                                "layout_type": s.layout_type,
                                "content_json": s.content_json,
                                "has_image": s.has_image,
                                "has_chart": s.has_chart,
                                "notes": s.notes,
                            }
                            for s in slides
                        ],
                    })
        except (json.JSONDecodeError, TypeError):
            pass

    elif name == "submit_evaluation" and output:
        try:
            result = json.loads(str(output))
            yield _sse("progress", {
                "step": "evaluated",
                "detail": f"评分: {result.get('total', '?')}/10",
                "pct": 80,
                "eval_result": result,
            })
        except (json.JSONDecodeError, TypeError):
            pass


async def _emit_final_outline(db: Database, conversation_id: int):
    """Emit the latest outline for this conversation."""
    outlines = await db.list_outlines_by_conversation(conversation_id)
    if not outlines:
        return
    outline = outlines[0]
    slides = await db.get_slides_by_outline_id(outline.id)
    yield _sse("outline", {
        "outline_id": outline.id,
        "title": outline.title,
        "version": outline.version,
        "slide_count": outline.slide_count,
        "eval_score": outline.eval_score,
        "slides": [
            {
                "slide_index": s.slide_index,
                "title": s.title,
                "layout_type": s.layout_type,
                "content_json": s.content_json,
                "has_image": s.has_image,
                "has_chart": s.has_chart,
                "notes": s.notes,
            }
            for s in slides
        ],
    })
