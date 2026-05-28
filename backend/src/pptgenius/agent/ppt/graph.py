"""PPT agent graph — two-phase pipeline with mode routing (sub_agent vs freedom).

Phase 1: StyleAgent selects color_scheme + layout
Phase 2: Supervisor dispatches per-slide → mode-dependent agents
Assembly: merge all agent outputs → validate → render .pptx
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from pptgenius.infrastructure.utils import get_logger

from .state import PPTState

_log = get_logger("pptgenius.agent.ppt")


# ── placeholder nodes (implemented in separate modules) ──


async def _create_presentation_node(state: PPTState, config) -> dict:
    """Create presentation record in DB, load outline slides."""
    from pptgenius.infrastructure.db import Database
    db: Database = config["configurable"]["db"]

    presentation_id = state.get("presentation_id")
    files_created = False
    if presentation_id is None:
        outline = await db.get_outline(state["outline_id"])
        pres = await db.create_presentation(
            user_id=state["user_id"],
            conversation_id=state["conversation_id"],
            outline_id=state["outline_id"],
            file_path=state["file_path"],
            status="style_selecting",
        )
        presentation_id = pres.id
        files_created = True

    # Load outline slides
    slides = await db.get_slides_by_outline_id(state["outline_id"])
    outline_slides = [
        {
            "slide_index": s.slide_index,
            "title": s.title,
            "content_json": s.content_json,
            "layout_type": s.layout_type,
            "has_image": s.has_image,
            "has_chart": s.has_chart,
            "notes": s.notes,
        }
        for s in slides
    ]

    return {
        "presentation_id": presentation_id,
        "outline_slides": outline_slides,
        "total_slides": len(slides),
        "current_slide_index": 0,
    }


async def _style_agent_node(state: PPTState, config) -> dict:
    """Phase 1: StyleAgent — select color_scheme + layouts."""
    # Built in phase1_style.py — placeholder for now
    _log.info("StyleAgent: color_scheme_id=%s template_id=%s",
              state.get("color_scheme_id"), state.get("template_id"))
    return {}


async def _supervisor_node(state: PPTState, config) -> dict:
    """Phase 2: Supervisor — per-slide dispatch."""
    # Built in phase2_sub_agent/supervisor.py or phase2_freedom/supervisor.py
    _log.info("Supervisor: slide %d/%d", state["current_slide_index"] + 1, state["total_slides"])
    return {}


async def _assembly_node(state: PPTState, config) -> dict:
    """Assembly: merge layout + agent outputs → validate → render .pptx."""
    from pptgenius.infrastructure.db import Database
    db: Database = config["configurable"]["db"]

    _log.info("Assembly: presentation_id=%d", state["presentation_id"])
    await db.update_presentation_status(state["presentation_id"], "completed")
    return {}


# ── routing ──


def _should_continue_phase2(state: PPTState) -> str:
    """Check if there are more slides to process."""
    if state["current_slide_index"] >= state["total_slides"]:
        return "assembly"
    return "supervisor"


def _route_style(state: PPTState) -> str:
    """Skip Phase 1 if style is already selected (modify without style change)."""
    if state.get("color_scheme_id") and state.get("template_id"):
        _log.info("Style already selected, skipping Phase 1")
        return "supervisor"
    return "style_agent"


# ── graph builder ──


def build_ppt_graph() -> StateGraph:
    """Build the PPT agent StateGraph."""
    builder = StateGraph(PPTState)

    builder.add_node("create_presentation", _create_presentation_node)
    builder.add_node("style_agent", _style_agent_node)
    builder.add_node("supervisor", _supervisor_node)
    builder.add_node("assembly", _assembly_node)

    # Edges
    builder.add_edge(START, "create_presentation")
    builder.add_conditional_edges("create_presentation", _route_style, {
        "style_agent": "style_agent",
        "supervisor": "supervisor",
    })
    builder.add_edge("style_agent", "supervisor")
    builder.add_conditional_edges("supervisor", _should_continue_phase2, {
        "supervisor": "supervisor",
        "assembly": "assembly",
    })
    builder.add_edge("assembly", END)

    return builder.compile()
