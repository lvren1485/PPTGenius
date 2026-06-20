"""Unified Master Agent — single entry point for all user requests."""

from __future__ import annotations

import asyncio
import uuid

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pptgenius.infrastructure.config.settings import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import TokenCounter, get_logger

from .common.middleware import build_middlewares
from .common.sse_context import get_sse_writer

_log = get_logger("pptgenius.agent.master")

# tool_name → content_type (≤32 chars, VARCHAR limit)
_TOOL_CTYPE: dict[str, str] = {
    "_get_conversation_status":  "conv_status",
    "_switch_outline":           "switch_outline",
    "_get_outline":              "get_outline",
    "_get_outline_slide":        "get_slide",
    "_get_presentation":         "get_pres",
    "_get_knowledge_files":      "get_kfiles",
    "_search_styles":            "search_styles",
    "_create_empty_outline":      "create_outline",
    "_write_outline_structure":  "write_outline",
    "_modify_outline_structure": "mod_outline",
    "_rearrange_presentation_slides": "rearr_pres",
    "_generate_outline_content": "gen_content",
    "_modify_outline_section":   "mod_section",
    "_outline_evaluate":         "evaluate",
    "_explore_knowledge":        "explore",
    "_ppt_style":                 "ppt_style",
    "_slides_content":            "slides_content",
    "_modify_slides_content":     "mod_slides",
}

# Tools that spawn a sub-agent (have their own LLM + TokenCountingMiddleware)
_SUB_AGENT_TOOLS: set[str] = {"gen_content", "mod_section", "evaluate", "explore", "ppt_style", "slides_content", "mod_slides"}

from pptgenius.infrastructure.llm import create_llm
from .tools.explore_knowledge import make_explore_knowledge
from .tools.outline_evaluate import make_outline_evaluate
from .tools.outline_section import make_generate_outline_content, make_modify_outline_section
from .tools.perception import (
    make_get_conversation_status,
    make_get_knowledge_files,
    make_get_outline,
    make_get_outline_slide,
    make_get_presentation,
    make_search_styles,
    make_switch_outline,
)
from .tools.ppt_style import make_ppt_style
from .tools.slides_content import make_modify_slides_content, make_slides_content
from .tools.structure import (
    make_create_empty_outline,
    make_modify_outline_structure,
    make_rearrange_presentation_slides,
    make_write_outline_structure,
)


def _assemble_tools(db: Database, conversation_id: int) -> list:
    """Assemble all currently-implemented Master tools."""
    return [
        # Perception 
        make_get_conversation_status(db, conversation_id),
        make_switch_outline(db, conversation_id),
        make_get_outline(db, conversation_id),
        make_get_outline_slide(db, conversation_id),
        make_get_presentation(db, conversation_id),
        make_get_knowledge_files(db, conversation_id),
        make_search_styles(db, conversation_id),
        # Structure
        make_create_empty_outline(db, conversation_id),
        make_write_outline_structure(db, conversation_id),
        make_modify_outline_structure(db, conversation_id),
        make_rearrange_presentation_slides(db, conversation_id),
        # Outline content 
        make_generate_outline_content(db, conversation_id),
        make_modify_outline_section(db, conversation_id),
        make_outline_evaluate(db, conversation_id),
        make_explore_knowledge(db, conversation_id),
        # Presentation content
        make_ppt_style(db, conversation_id),
        make_slides_content(db, conversation_id),
        make_modify_slides_content(db, conversation_id),
    ]




async def run_master_agent(
    db: Database,
    conversation_id: int,
    user_message: str,
    *,
    recursion_limit: int = 50,
) -> dict:
    """Run the Unified Master Agent for one user turn.

    Returns ``{"reply": str, "outline_changed": bool, "presentation_changed": bool}``.
    """
    writer = get_sse_writer()

    # --- 1. Build LLM + middleware ---
    llm, agent_id = create_llm(conversation_id)
    mws, persist_mw = build_middlewares(
        conversation_id, agent_id,
        ctypes=_TOOL_CTYPE, sub_agent_types=_SUB_AGENT_TOOLS,
    )
    _log.info("master agent start conv=%d agent=%s", conversation_id, agent_id)

    # --- 2. Assemble tools ---
    tools = _assemble_tools(db, conversation_id)
    _log.debug("assembled %d tools for conv=%d", len(tools), conversation_id)

    # --- 3. Build agent ---
    prompt_path = RESOURCES_DIR / "prompts" / "master.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=mws,
    )

    # --- 4. Load context + run ---
    writer({"type": "master_start"})
    context = await _load_context_messages(db, conversation_id)
    context.append(HumanMessage(content=user_message))
    state = {"messages": context}
    _log.debug("loaded %d context messages for conv=%d", len(context) - 1, conversation_id)
    error_msg = ""
    try:
        result = await agent.ainvoke(state, config={"recursion_limit": recursion_limit})
    except asyncio.CancelledError:
        error_msg = "已取消"
        result = {"messages": context}
    except Exception as e:
        _log.warning("master agent crashed conv=%d: %s", conversation_id, e)
        _log.debug("master crash detail", exc_info=True)
        error_msg = f"出错了，内容如下：{str(e)}，请联系管理员修复错误。"
        result = {"messages": context}

    writer({"type": "master_done"})
    _log.info("master agent done conv=%d agent=%s", conversation_id, agent_id)

    # --- 5. Persist tool messages + sub-agent tokens ---
    await persist_mw.flush(db)

    # --- 6. Extract reply ---
    if error_msg:
        reply = error_msg
    else:
        reply = ""
        messages = result.get("messages", [])
        if messages:
            last = messages[-1]
            reply = last.content if hasattr(last, "content") else str(last)
        if not reply:
            reply = "操作已完成。您可以使用 get_outline 查看结果。"

    # --- 7. Persist Master's own token cost ---
    tc = TokenCounter.get_agent(agent_id)
    # Persist context usage before removing the counter
    if tc and tc.total_tokens > 0:
        await db.update_context_usage(
            conversation_id,
            round(tc.total_tokens / 1_000_000, 4),
        )
    TokenCounter.remove_agent(agent_id)  # prevent memory leak
    # Extract reasoning_content from the last AIMessage in the result chain
    reasoning = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.additional_kwargs.get("reasoning_content"):
            reasoning = m.additional_kwargs["reasoning_content"]
            break
    meta = {"reasoning_content": reasoning} if reasoning else None
    await db.create_message(
        conversation_id=conversation_id,
        role="assistant",
        content=reply,
        content_type="text",
        estimated_cost=tc.snapshot()["estimated_cost_cny"] if tc else 0.0,
        token_cost_json=tc.to_json() if tc else None,
        metadata_json=meta,
    )

    # --- 8. Snapshot on exit ---
    outline_snapshot_id = None
    pres_snapshot_id = None
    outline_changed = _has_outline_changed(result)
    presentation_changed = _has_presentation_changed(result)

    _log.debug("conv=%d outline_changed=%s presentation_changed=%s",
               conversation_id, outline_changed, presentation_changed)

    if outline_changed:
        conv = await db.get_conversation(conversation_id)
        if conv and conv.current_outline_id:
            await db.increase_outline_version(conv.current_outline_id)
            outline = await db.get_outline(conv.current_outline_id)
            if outline:
                snap = await db.create_outline_snapshot(
                    outline_id=conv.current_outline_id,
                    user_id=outline.user_id,
                    conversation_id=conversation_id,
                    outline_version=outline.version,
                    outline_json=_build_outline_snapshot_json(
                        outline,
                        await db.get_sections_by_outline_id(conv.current_outline_id),
                        await db.get_slides_by_outline_id(conv.current_outline_id),
                    ),
                )
                await db.create_message(
                    conversation_id=conversation_id,
                    role="document",
                    content=str(snap.id),
                    content_type="outline",
                )
                outline_snapshot_id = snap.id

    if presentation_changed:
        conv = await db.get_conversation(conversation_id)
        if conv and conv.current_outline_id:
            pres_list = await db.list_presentations_by_conversation(conversation_id)
            pres = next(
                (p for p in pres_list
                 if p.outline_id == conv.current_outline_id and p.status != "deleted"),
                None,
            )
            if pres:
                await db.increment_presentation_version(pres.id)
                pres = await db.get_presentation(pres.id)
                outline = await db.get_outline(conv.current_outline_id)
                slides = await db.get_slides_by_presentation_id(pres.id)
                snap = await db.create_snapshot(
                    presentation_id=pres.id,
                    user_id=pres.user_id,
                    conversation_id=conversation_id,
                    outline_version=pres.outline_version,
                    presentation_json=_build_presentation_snapshot_json(pres, slides),
                    pres_version=pres.version,
                )
                await db.create_message(
                    conversation_id=conversation_id,
                    role="document",
                    content=str(snap.id),
                    content_type="presentation",
                )
                pres_snapshot_id = snap.id

    # Ensure all DB changes are committed before the session closes
    await db.db.commit()

    return {
        "reply": reply,
        "outline_changed": outline_changed,
        "presentation_changed": presentation_changed,
        "outline_snapshot_id": outline_snapshot_id,
        "presentation_snapshot_id": pres_snapshot_id,
    }


async def _load_context_messages(
    db: Database, conversation_id: int, *, max_turns: int = 20,
) -> list:
    """Load recent messages from DB, reconstruct LangChain message chain.

    Only emits complete AIMessage(tool_calls) → ToolMessage pairs.
    Incomplete pairs (from partial persistence) are silently dropped.
    """
    rows = await db.get_messages_by_conversation(conversation_id)
    rows = rows[-max_turns:]

    msgs: list = []
    # Pending tool_calls keyed by tool_call_id (handles parallel calls)
    pending: dict[str, dict] = {}

    for r in rows:
        if r.role == "user" and r.content_type == "text":
            pending.clear()
            msgs.append(HumanMessage(content=r.content))

        elif r.role in ("file", "image") and r.content:
            pending.clear()
            msgs.append(HumanMessage(content=r.content))

        elif r.role == "tool_call":
            meta = r.metadata_json or {}
            tc_id = meta.get("tool_call_id", "") or str(uuid.uuid4())
            pending[tc_id] = {
                "name": meta.get("tool_name", ""),
                "args": meta.get("args", {}),
                "id": tc_id,
                "type": "tool_call",
            }
            reasoning = meta.get("reasoning_content", "")
            if reasoning:
                pending[tc_id + "_reasoning"] = reasoning

        elif r.role == "tool_result":
            meta = r.metadata_json or {}
            tc_id = meta.get("tool_call_id", "") or ""
            tc = pending.pop(tc_id, None)
            reasoning = pending.pop(tc_id + "_reasoning", "") or ""
            if tc:
                extra = {"reasoning_content": reasoning} if reasoning else {}
                msgs.append(AIMessage(content="", tool_calls=[tc], additional_kwargs=extra))
                msgs.append(ToolMessage(
                    content=r.content,
                    tool_call_id=tc_id,
                    name=meta.get("tool_name", ""),
                ))

        elif r.role == "assistant" and r.content_type == "text":
            pending.clear()
            meta = r.metadata_json or {}
            reasoning = meta.get("reasoning_content", "")
            extra = {"reasoning_content": reasoning} if reasoning else {}
            msgs.append(AIMessage(content=r.content, additional_kwargs=extra))

    return msgs


def _has_outline_changed(state: dict) -> bool:
    """Heuristic: check if any structure/perception tools were called."""
    msgs = state.get("messages", [])
    # If there are tool message results from write_outline_structure or
    # modify_outline_structure, assume outline changed.
    for m in msgs:
        name = getattr(m, "name", "")
        if name in ("_write_outline_structure", "_modify_outline_structure",
                     "_generate_outline_content", "_modify_outline_section"):
            return True
    return False


def _has_presentation_changed(state: dict) -> bool:
    msgs = state.get("messages", [])
    for m in msgs:
        name = getattr(m, "name", "")
        if name in ("_slides_content", "_ppt_style", "_rearrange_presentation_slides"):
            return True
    return False


def _build_outline_snapshot_json(outline, sections, slides) -> dict:
    return {
        "title": outline.title,
        "status": outline.status,
        "version": str(outline.version),
        "slide_count": outline.slide_count,
        "eval_score": outline.eval_score,
        "sections": [
            {
                "section_index": s.section_index,
                "title": s.title,
                "description": s.description,
                "slides": [
                    {
                        "slide_index": sl.slide_index,
                        "title": sl.title,
                        "layout_type": sl.layout_type,
                        "status": sl.status,
                        "content_json": sl.content_json,
                        "notes": sl.notes,
                        "has_image": sl.has_image,
                        "has_chart": sl.has_chart,
                        "citations": sl.citations,
                    }
                    for sl in slides if sl.section_id == s.id
                ],
            }
            for s in sections
        ],
    }


def _build_presentation_snapshot_json(pres, slides) -> dict:
    return {
        "status": pres.status,
        "style_id": pres.style_id,
        "slide_count": pres.slide_count,
        "version": pres.version,
        "outline_version": pres.outline_version,
        "slides": [
            {
                "slide_index": s.slide_index,
                "layout_name": s.layout_name,
                "status": s.status,
                "agent_outputs": s.agent_outputs,
            }
            for s in slides
        ],
    }
