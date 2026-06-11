"""Unified Master Agent — single entry point for all user requests."""

from __future__ import annotations

import uuid

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.config.settings import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import TokenCounter, get_logger

from .common.agent_registry import pop_until_sentinel

_log = get_logger("pptgenius.agent.master")

# tool_name → content_type (≤32 chars, VARCHAR limit)
# Tool names come from inner function __name__ (wrap_tool_with_sse preserves it)
_TOOL_CTYPE: dict[str, str] = {
    "_get_conversation_status":  "conv_status",
    "_switch_outline":           "switch_outline",
    "_get_outline":              "get_outline",
    "_get_outline_slide":        "get_slide",
    "_get_presentation":         "get_pres",
    "_get_knowledge_files":      "get_kfiles",
    "_list_styles":              "list_styles",
    "_write_outline_structure":  "write_outline",
    "_modify_outline_structure": "mod_outline",
    "_generate_outline_content": "gen_content",
    "_modify_outline_section":   "mod_section",
    "_outline_evaluate":         "evaluate",
    "_explore_knowledge":        "explore",
}

# Tools that spawn a sub-agent (have their own LLM + TokenCountingMiddleware)
_SUB_AGENT_TOOLS: set[str] = {"gen_content", "mod_section", "evaluate", "explore"}

from .common.model_builder import build_llm
from .tools.explore_knowledge import make_explore_knowledge
from .tools.outline_evaluate import make_outline_evaluate
from .tools.outline_section import make_generate_outline_content, make_modify_outline_section
from .tools.perception import (
    make_get_conversation_status,
    make_get_knowledge_files,
    make_get_outline,
    make_get_outline_slide,
    make_get_presentation,
    make_list_styles,
    make_switch_outline,
)
from .tools.structure import make_modify_outline_structure, make_write_outline_structure


def _assemble_tools(db: Database, conversation_id: int) -> list:
    """Assemble all currently-implemented Master tools."""
    return [
        # Perception (Phase 2)
        make_get_conversation_status(db, conversation_id),
        make_switch_outline(db, conversation_id),
        make_get_outline(db, conversation_id),
        make_get_outline_slide(db, conversation_id),
        make_get_presentation(db, conversation_id),
        make_get_knowledge_files(db, conversation_id),
        make_list_styles(db, conversation_id),
        # Structure (Phase 2)
        make_write_outline_structure(db, conversation_id),
        make_modify_outline_structure(db, conversation_id),
        # Outline content (Phase 3 — thin wrappers over outline/)
        make_generate_outline_content(db, conversation_id),
        make_modify_outline_section(db, conversation_id),
        make_outline_evaluate(db, conversation_id),
        make_explore_knowledge(db, conversation_id),
        # ppt_style (Phase 4) — TODO
        # slides_content (Phase 4) — TODO
    ]


def _build_sse_writer():
    """Get stream writer or no-op fallback."""
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _: None


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
    writer = _build_sse_writer()

    # --- 1. Build LLM + middleware ---
    llm, agent_id, mw = build_llm(conversation_id)
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
        middleware=[mw],
    )

    # --- 4. Load context + run ---
    writer({"type": "master_start"})
    context = await _load_context_messages(db, conversation_id)
    context.append(HumanMessage(content=user_message))
    state = {"messages": context}
    _log.debug("loaded %d context messages for conv=%d", len(context) - 1, conversation_id)
    result = await agent.ainvoke(state, config={"recursion_limit": recursion_limit})
    writer({"type": "master_done"})
    _log.info("master agent done conv=%d agent=%s", conversation_id, agent_id)

    # --- 5. Persist tool messages + sub-agent tokens (deduplicated by tool_call_id) ---
    await _persist_tool_messages(db, conversation_id, result["messages"])

    # --- 6. Extract reply ---
    reply = ""
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        reply = last.content if hasattr(last, "content") else str(last)

    # --- 7. Persist Master's own token cost ---
    tc = TokenCounter.get_agent(agent_id)
    if tc:
        await db.create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=reply,
            content_type="text",
            estimated_cost=tc.snapshot()["estimated_cost_cny"],
            token_cost_json=tc.to_json(),
        )

    # --- 8. Snapshot on exit ---
    outline_changed = _has_outline_changed(result)
    presentation_changed = _has_presentation_changed(result)

    _log.debug("conv=%d outline_changed=%s presentation_changed=%s",
               conversation_id, outline_changed, presentation_changed)

    if outline_changed:
        conv = await db.get_conversation(conversation_id)
        if conv and conv.current_outline_id:
            await db.increase_outline_version(conv.current_outline_id, "patch")
            outline = await db.get_outline(conv.current_outline_id)
            if outline:
                await db.create_outline_snapshot(
                    outline_id=conv.current_outline_id,
                    user_id=outline.user_id,
                    conversation_id=conversation_id,
                    outline_json=_build_outline_snapshot_json(
                        outline,
                        await db.get_sections_by_outline_id(conv.current_outline_id),
                        await db.get_slides_by_outline_id(conv.current_outline_id),
                    ),
                )

    # Ensure all DB changes are committed before the session closes
    await db.db.commit()

    return {
        "reply": reply,
        "outline_changed": outline_changed,
        "presentation_changed": presentation_changed,
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

        elif r.role == "tool_result":
            meta = r.metadata_json or {}
            tc_id = meta.get("tool_call_id", "") or ""
            tc = pending.pop(tc_id, None)
            if tc:
                msgs.append(AIMessage(content="", tool_calls=[tc]))
                msgs.append(ToolMessage(
                    content=r.content,
                    tool_call_id=tc_id,
                    name=meta.get("tool_name", ""),
                ))

        elif r.role == "assistant" and r.content_type == "text":
            pending.clear()
            msgs.append(AIMessage(content=r.content))

    return msgs


async def _persist_tool_messages(
    db: Database, conversation_id: int, messages: list,
) -> None:
    """Persist tool_call / tool_result message pairs with token costs.

    Stores LangChain's tool_call_id so _load_context_messages can
    reconstruct AIMessage(tool_calls) + ToolMessage pairs correctly.
    Deduplicates by tool_call_id — messages already persisted from
    earlier turns are skipped.
    """
    # Collect already-persisted tool_call_ids for this conversation
    existing = await db.get_messages_by_conversation(conversation_id)
    seen_ids: set[str] = set()
    for r in existing:
        meta = r.metadata_json or {}
        tc_id = meta.get("tool_call_id", "")
        if tc_id:
            seen_ids.add(tc_id)

    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                tc_id = tc.get("id", "")
                if tc_id in seen_ids:
                    continue  # already persisted from a previous turn
                ctype = _TOOL_CTYPE.get(tc.get("name", ""), "tool_call")
                await db.create_message(
                    conversation_id=conversation_id,
                    role="tool_call",
                    content=tc.get("args", {}).get("query", "") or "",
                    content_type=ctype,
                    metadata_json={
                        "tool_name": tc.get("name"),
                        "args": tc.get("args", {}),
                        "tool_call_id": tc.get("id", ""),
                    },
                )

        elif isinstance(m, ToolMessage):
            tc_id = getattr(m, "tool_call_id", "") or ""
            if tc_id in seen_ids:
                continue  # already persisted from a previous turn
            name = getattr(m, "name", "") or ""
            ctype = _TOOL_CTYPE.get(name, "tool_result")
            tool_content = str(m.content) if hasattr(m, "content") else ""

            msg = await db.create_message(
                conversation_id=conversation_id,
                role="tool_result",
                content=tool_content,
                content_type=ctype,
                metadata_json={"tool_name": name, "tool_call_id": tc_id},
            )

            # For sub-agent tools, flush all concurrent agent token counters
            if ctype in _SUB_AGENT_TOOLS:
                agent_ids = pop_until_sentinel(conversation_id)
                if agent_ids:
                    summed: dict = {}
                    total_cost = 0.0
                    for aid in agent_ids:
                        tc = TokenCounter.get_agent(aid)
                        if tc:
                            for k, v in tc.to_json().items():
                                summed[k] = summed.get(k, 0) + v
                            total_cost += tc.snapshot()["estimated_cost_cny"]
                    await db.set_message_cost(msg.id,
                        token_cost_json=summed,
                        estimated_cost=total_cost,
                    )
                    _log.debug("persisted tokens for tool=%s agents=%d msg=%d cost=%.4f",
                               ctype, len(agent_ids), msg.id, total_cost)


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
        if name in ("_slides_content", "_ppt_style"):
            return True
    return False


def _build_outline_snapshot_json(outline, sections, slides) -> dict:
    return {
        "title": outline.title,
        "status": outline.status,
        "version": f"{outline.version_major}.{outline.version_minor}.{outline.version_patch}",
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
