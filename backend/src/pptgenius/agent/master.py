"""Unified Master Agent — single entry point for all user requests."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.config.settings import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import TokenCounter

from .common.model_builder import build_llm
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
        # Outline content (Phase 2 stubs, Phase 3 real)
        make_generate_outline_content(db, conversation_id),
        make_modify_outline_section(db, conversation_id),
        # outline_evaluate (Phase 3) — TODO
        # summarize_file (Phase 3) — TODO
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
    # Master agent persists its own token cost to a message row
    llm, agent_id, mw = build_llm(conversation_id)

    # --- 2. Assemble tools ---
    tools = _assemble_tools(db, conversation_id)

    # --- 3. Build agent ---
    prompt_path = RESOURCES_DIR / "prompts" / "master.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[mw],
    )

    # --- 4. Run ---
    writer({"type": "master_start"})
    state = {"messages": [HumanMessage(content=user_message)]}
    result = await agent.ainvoke(state, config={"recursion_limit": recursion_limit})
    writer({"type": "master_done"})

    # --- 5. Extract reply ---
    reply = ""
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        reply = last.content if hasattr(last, "content") else str(last)

    # --- 6. Persist Master's own token cost ---
    tc = TokenCounter.get_agent(agent_id)
    if tc:
        snap = tc.snapshot()
        cost = tc.estimate_cost()
        # Create message row for the master's own text response
        await db.create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=reply,
            content_type="text",
            estimated_cost=cost,
            token_cost_json={
                "input_tokens": snap["prompt_tokens"],
                "output_tokens": snap["completion_tokens"],
                "total_tokens": snap["total_tokens"],
                "cache_tokens": snap["cache_tokens"],
            },
        )

    # --- 7. Snapshot on exit ---
    outline_changed = _has_outline_changed(result)
    presentation_changed = _has_presentation_changed(result)

    if outline_changed:
        await db.increase_outline_version(conv.current_outline_id, "patch")

    if outline_changed:
        conv = await db.get_conversation(conversation_id)
        if conv and conv.current_outline_id:
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

    return {
        "reply": reply,
        "outline_changed": outline_changed,
        "presentation_changed": presentation_changed,
    }


def _has_outline_changed(state: dict) -> bool:
    """Heuristic: check if any structure/perception tools were called."""
    msgs = state.get("messages", [])
    # If there are tool message results from write_outline_structure or
    # modify_outline_structure, assume outline changed.
    for m in msgs:
        name = getattr(m, "name", "")
        if name in ("write_outline_structure", "modify_outline_structure",
                     "generate_outline_content", "modify_outline_section"):
            return True
    return False


def _has_presentation_changed(state: dict) -> bool:
    msgs = state.get("messages", [])
    for m in msgs:
        name = getattr(m, "name", "")
        if name in ("slides_content", "ppt_style"):
            return True
    return False


def _build_outline_snapshot_json(outline, sections, slides) -> dict:
    return {
        "title": outline.title,
        "status": outline.status,
        "version": f"{outline.version_major}.{outline.version_minor}.{outline.version_patch}",
        "slide_count": outline.slide_count,
        "sections": [
            {
                "section_index": s.section_index,
                "title": s.title,
                "slides": [
                    {
                        "slide_index": sl.slide_index,
                        "title": sl.title,
                        "layout_type": sl.layout_type,
                        "status": sl.status,
                    }
                    for sl in slides if sl.section_id == s.id
                ],
            }
            for s in sections
        ],
    }
