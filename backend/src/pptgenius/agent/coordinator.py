"""Coordinator agent — intent classification + sub-agent dispatch.

Analyses the user message and current conversation state (loaded from DB),
then routes to the outline agent or PPT agent.  Accumulates token usage,
stores assistant messages, and emits full token + outline summaries.
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.agent.outline import OutlineState, build_outline_graph
from pptgenius.agent.ppt import build_ppt_graph
from pptgenius.infrastructure.config import RESOURCES_DIR, get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import TokenCounter, get_logger

apply_deepseek_patch()

_log = get_logger("pptgenius.agent.coordinator")

_PROMPT_PATH = RESOURCES_DIR / "prompts" / "coordinator_system.txt"


# ── structured output model ──────────────────────────────────────────────────


class CoordinatorDecision(BaseModel):
    task: Literal[
        "generate_outline", "modify_outline", "generate_ppt", "modify_ppt",
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
    return "You are a PPT assistant coordinator. Classify the user intent."


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── conversation state tool ──────────────────────────────────────────────────


def _make_get_state(db: Database, conversation_id: int):
    @tool
    async def get_conversation_state(dummy: str = "") -> str:
        """Get the current conversation's PPT and outline status.

        Use this to check what already exists before deciding the task.
        Pass an empty string as the argument.
        """
        outlines = await db.list_outlines_by_conversation(conversation_id)
        presentations = await db.list_presentations_by_conversation(conversation_id)

        return json.dumps({
            "has_outline": len(outlines) > 0,
            "outline_count": len(outlines),
            "latest_outline": {
                "id": outlines[0].id, "title": outlines[0].title,
                "version": outlines[0].version, "eval_score": outlines[0].eval_score,
                "status": outlines[0].status, "slide_count": outlines[0].slide_count,
            } if outlines else None,
            "has_ppt": len(presentations) > 0,
            "ppt_count": len(presentations),
            "latest_ppt": {
                "id": presentations[0].id, "status": presentations[0].status,
                "file_path": presentations[0].file_path,
                "slide_count": presentations[0].slide_count,
            } if presentations else None,
        }, ensure_ascii=False)

    return get_conversation_state


# ── intent classification ────────────────────────────────────────────────────


async def _classify_intent(
    query: str,
    has_outline: bool,
    has_ppt: bool,
    outline_title: str = "",
    history_summary: str = "",
) -> CoordinatorDecision:
    """Use LLM (with conversation state context) to classify user intent."""
    model = _get_model()
    # DeepSeek V4 Flash doesn't support json_schema mode; use json_mode
    structured_model = model.with_structured_output(CoordinatorDecision, method="json_mode")
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
    tc = TokenCounter.for_conversation(conversation_id)
    conv = await db.get_conversation(conversation_id)
    if conv is None:
        yield _sse("error", {"code": 40001, "message": "conversation not found", "retryable": False})
        return

    user_id = conv.user_id

    # --- load current state from DB ---
    outlines = await db.list_outlines_by_conversation(conversation_id)
    presentations = await db.list_presentations_by_conversation(conversation_id)
    latest_outline = outlines[0] if outlines else None
    latest_ppt = presentations[0] if presentations else None

    # --- load conversation history for cache / context ---
    history_messages = await db.get_messages_by_conversation(conversation_id)
    history_summary = ""
    if history_messages:
        recent = history_messages[-10:]  # last 10 messages
        lines = []
        for m in recent:
            role = "用户" if m.role == "user" else "助手"
            content_preview = (m.content or "")[:200]
            lines.append(f"[{role}]: {content_preview}")
        history_summary = "\n".join(lines)

    # --- classify intent ---
    decision = await _classify_intent(
        query=query,
        has_outline=latest_outline is not None,
        has_ppt=latest_ppt is not None,
        outline_title=latest_outline.title if latest_outline else "",
        history_summary=history_summary,
    )

    yield _sse("progress", {
        "step": "coordinator_decision",
        "detail": f"协调Agent判断: {decision.task}",
        "reasoning": decision.reasoning,
        "pct": 5,
    })

    # --- dispatch ---
    if decision.task in ("generate_outline", "modify_outline"):
        async for event in _run_outline(
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            existing_outline=latest_outline,
            is_modify=(decision.task == "modify_outline"),
        ):
            yield event

    elif decision.task in ("generate_ppt", "modify_ppt"):
        async for event in _run_ppt(
            db=db, user_id=user_id, conversation_id=conversation_id,
            query=query, outline=latest_outline, existing_ppt=latest_ppt,
        ):
            yield event

    # --- token summary ---
    snapshot = tc.snapshot()
    yield _sse("tokens", snapshot)

    # --- store assistant message ---
    design_rationales = list(_rationale_store) if _rationale_store else None
    assistant_content = _build_assistant_content(decision, latest_outline, design_rationales)
    await db.create_message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        content_type="text",
        estimated_cost=snapshot["estimated_cost_cny"],
    )
    yield _sse("message_stored", {"role": "assistant", "length": len(assistant_content)})


# ── assistant content builder ────────────────────────────────────────────────


def _build_assistant_content(
    decision: CoordinatorDecision,
    outline,
    design_rationales: list[str] | None,
) -> str:
    """Build a readable assistant message summarising what was done."""
    task_labels = {
        "generate_outline": "大纲生成",
        "modify_outline": "大纲修改",
        "generate_ppt": "PPT生成",
        "modify_ppt": "PPT修改",
    }
    label = task_labels.get(decision.task, decision.task)
    parts = [f"## 协调Agent执行任务: {label}", "", f"**判断依据**: {decision.reasoning}"]

    if outline:
        parts.append(f"\n**大纲**: {outline.title} (ID={outline.id}, v{outline.version}, 评分={outline.eval_score})")

    if design_rationales:
        parts.append("\n### 设计思路")
        for i, r in enumerate(design_rationales, 1):
            parts.append(f"\n**第{i}轮**: {r}")

    return "\n".join(parts)


# ── outline sub-agent runner ─────────────────────────────────────────────────


_rationale_store: list[str] = []


async def _run_outline(
    db: Database,
    user_id: int,
    conversation_id: int,
    query: str,
    existing_outline,
    is_modify: bool,
) -> AsyncGenerator[str, None]:
    """Run the outline generator-evaluator graph and stream events."""
    cfg = get_settings().agent.outline

    state: OutlineState = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "query": query,
        "outline_id": existing_outline.id if existing_outline else None,
        "evaluated": is_modify,
        "iteration": 0,
        "eval_score": existing_outline.eval_score if existing_outline else None,
        "eval_suggestions": "",
        "mode": cfg.mode,
        "max_iterations": cfg.max_iterations,
        "pass_score": cfg.pass_score,
        "design_rationale": "",
        "design_rationales": [],
        "final_outline_data": None,
        "messages": [],
    }

    graph = build_outline_graph()

    phase_msg = "开始修改大纲..." if is_modify else "开始生成大纲..."
    yield _sse("phase", {"phase": "outline", "message": phase_msg})

    try:
        async for event in graph.astream_events(
            state, config={"configurable": {"db": db}}, version="v2",
        ):
            kind = event["event"]

            if kind == "on_tool_start":
                async for sse in _tool_start_sse(event):
                    yield sse

            elif kind == "on_tool_end":
                async for sse in _tool_end_sse(event, db):
                    yield sse

            elif kind == "on_custom_event":
                # Events pushed via get_stream_writer() from generator/evaluator nodes
                custom_data = event.get("data", {})
                if custom_data.get("type") == "generator_start":
                    _log.debug("generator started via stream_writer")
                elif custom_data.get("type") == "generator_end":
                    _log.debug("generator ended via stream_writer")

            elif kind == "on_chain_end" and event["name"] == "finalize":
                # Outline graph finished — emit final outline data directly
                output = event["data"].get("output", {})
                final_data = output.get("final_outline_data")
                design_rationales = output.get("design_rationales", [])
                _rationale_store.clear()
                _rationale_store.extend(design_rationales)

                if final_data:
                    yield _sse("outline", final_data)
                yield _sse("phase", {
                    "phase": "waiting_user",
                    "message": "大纲已就绪，请确认或提出修改意见",
                })

    except Exception:
        _log.exception("outline agent error — attempting recovery")
        # Try to recover: read any outline that was created
        outlines = await db.list_outlines_by_conversation(conversation_id)
        if outlines:
            o = outlines[0]
            slides = await db.get_slides_by_outline_id(o.id)
            yield _sse("outline", {
                "outline_id": o.id, "title": o.title,
                "version": o.version, "slide_count": o.slide_count,
                "eval_score": o.eval_score,
                "slides": [
                    {
                        "slide_index": s.slide_index, "title": s.title,
                        "layout_type": s.layout_type, "content_json": s.content_json,
                        "has_image": s.has_image, "has_chart": s.has_chart, "notes": s.notes,
                    }
                    for s in slides
                ],
            })
            yield _sse("phase", {
                "phase": "waiting_user",
                "message": "大纲生成过程出错，已恢复最后保存的版本",
            })
        else:
            yield _sse("error", {"code": 40200, "message": "大纲生成失败，请重试", "retryable": True})


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

    from pptgenius.agent.ppt import build_ppt_graph
    from pptgenius.agent.ppt.state import PPTState

    cfg = get_settings().agent
    ppt_mode = getattr(cfg, "ppt", None)
    mode = getattr(ppt_mode, "mode", "sub_agent") if ppt_mode else "sub_agent"

    state: PPTState = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "query": query,
        "outline_id": outline.id,
        "is_modify": existing_ppt is not None,
        "presentation_id": existing_ppt.id if existing_ppt else None,
        "color_scheme_id": existing_ppt.color_scheme_id if existing_ppt else None,
        "template_id": existing_ppt.template_id if existing_ppt else None,
        "selected_layouts": {},
        "style_rationale": "",
        "current_slide_index": 0,
        "total_slides": outline.slide_count or 0,
        "ppt_mode": mode,
        "outline_slides": [],
        "design_rationales": [],
        "file_path": f"output/{outline.title}.pptx",
        "messages": [],
    }

    graph = build_ppt_graph()

    yield _sse("phase", {"phase": "ppt", "message": "开始生成PPT..."})

    import time as _time
    t_start = _time.monotonic()

    try:
        async for event in graph.astream_events(
            state, config={"configurable": {"db": db}}, version="v2",
        ):
            kind = event["event"]

            if kind == "on_custom_event":
                custom_data = event.get("data", {})
                etype = custom_data.get("type", "")
                if etype == "slide_start":
                    yield _sse("progress", {
                        "step": "slide_generating",
                        "detail": f"第{custom_data['slide_index'] + 1}/{custom_data['total']}页: {custom_data.get('title', '')}",
                        "pct": 10 + int(80 * (custom_data['slide_index'] + 1) / max(custom_data['total'], 1)),
                    })
                elif etype == "slide_end":
                    yield _sse("progress", {
                        "step": "slide_done",
                        "detail": f"第{custom_data['slide_index'] + 1}页完成 ({custom_data.get('elapsed', 0)}s)",
                        "pct": 10 + int(80 * (custom_data['slide_index'] + 1) / max(state['total_slides'], 1)),
                    })

            elif kind == "on_chain_end" and event["name"] == "assembly":
                t_end = _time.monotonic()
                output = event["data"].get("output", {})
                yield _sse("phase", {
                    "phase": "ppt_done",
                    "message": f"PPT生成完成 (耗时 {t_end - t_start:.1f}s)",
                })
                yield _sse("ppt_done", {
                    "presentation_id": state["presentation_id"],
                    "file_path": state["file_path"],
                    "elapsed_seconds": round(t_end - t_start, 1),
                    "mode": mode,
                })

    except Exception:
        _log.exception("PPT agent error")
        yield _sse("error", {"code": 40400, "message": "PPT生成失败，请重试", "retryable": True})


# ── SSE event helpers ────────────────────────────────────────────────────────


async def _tool_start_sse(event: dict):
    name = event["name"]
    label_map = {
        "search_knowledge": ("searching_knowledge", "检索知识库...", 10),
        "search_web": ("searching_web", "搜索网络...", 20),
        "fetch_web": ("fetching_web", "获取网页内容...", 30),
        "write_outline": ("writing_outline", "正在生成大纲...", 50),
        "submit_evaluation": ("evaluating", "评估中...", 70),
        "get_conversation_state": ("loading_state", "加载会话状态...", 2),
    }
    if name in label_map:
        step, detail, pct = label_map[name]
        yield _sse("progress", {"step": step, "detail": detail, "pct": pct})


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
                        "outline_id": outline.id, "title": outline.title,
                        "version": outline.version, "slide_count": outline.slide_count,
                        "slides": [
                            {
                                "slide_index": s.slide_index, "title": s.title,
                                "layout_type": s.layout_type, "content_json": s.content_json,
                                "has_image": s.has_image, "has_chart": s.has_chart, "notes": s.notes,
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
