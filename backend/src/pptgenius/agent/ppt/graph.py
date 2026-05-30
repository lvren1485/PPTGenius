"""PPT agent graph — two-phase pipeline with mode routing (sub_agent vs freedom).

Phase 1: StyleAgent selects color_scheme + layout
Phase 2: Supervisor dispatches per-slide → mode-dependent agents
Assembly: merge all agent outputs → validate → render .pptx
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from pptgenius.infrastructure.utils import get_logger

from .phase1_style import style_agent_node
from .phase2_sub_agent.supervisor import supervisor_node as sub_agent_supervisor
from .phase2_freedom.supervisor import freedom_supervisor_node
from .state import PPTState

_log = get_logger("pptgenius.agent.ppt")


# ── nodes ─────────────────────────────────────────────────────────────────────


async def _create_presentation_node(state: PPTState, config) -> dict:
    """Create presentation record in DB, load outline slides."""
    from pptgenius.infrastructure.db import Database
    db: Database = config["configurable"]["db"]

    presentation_id = state.get("presentation_id")
    if presentation_id is None:
        pres = await db.create_presentation(
            user_id=state["user_id"],
            conversation_id=state["conversation_id"],
            outline_id=state["outline_id"],
        )
        presentation_id = pres.id

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

    # Load template layouts for supervisor
    selected_layouts = state.get("selected_layouts", {})
    if not selected_layouts:
        templates = await db.list_active_templates()
        if templates:
            selected_layouts = templates[0].layouts_json or {}

    return {
        "presentation_id": presentation_id,
        "outline_slides": outline_slides,
        "total_slides": len(slides),
        "current_slide_index": 0,
        "selected_layouts": selected_layouts,
    }


async def _supervisor_node(state: PPTState, config) -> dict:
    """Phase 2: Supervisor — per-slide dispatch, mode-aware."""
    mode = state.get("ppt_mode", "sub_agent")
    if mode == "freedom":
        return await freedom_supervisor_node(state, config)
    return await sub_agent_supervisor(state, config)


async def _assembly_node(state: PPTState, config) -> dict:
    """Assembly: merge layout + agent outputs → validate → render .pptx, then snapshot."""
    from pptgenius.infrastructure.db import Database
    db: Database = config["configurable"]["db"]

    pres_id = state["presentation_id"]
    _log.info("Assembly: presentation_id=%d", pres_id)

    # Collect outline + presentation data for snapshot
    outline = await db.get_outline(state["outline_id"])
    pres = await db.get_presentation(pres_id)
    slides = await db.get_slides_by_presentation_id(pres_id)

    outline_data = None
    if outline:
        outline_slides = await db.get_slides_by_outline_id(outline.id)
        outline_data = {
            "id": outline.id, "title": outline.title, "version": outline.version,
            "slide_count": outline.slide_count, "eval_score": outline.eval_score,
            "slides": [
                {"slide_index": s.slide_index, "title": s.title,
                 "layout_type": s.layout_type, "content_json": s.content_json}
                for s in outline_slides
            ],
        }

    presentation_data = {
        "id": pres.id if pres else pres_id,
        "slide_count": len(slides),
        "color_scheme_id": state.get("color_scheme_id"),
        "template_id": state.get("template_id"),
        "slides": [
            {"slide_index": s.slide_index, "layout_name": s.layout_name,
             "agent_outputs": s.agent_outputs, "status": s.status}
            for s in slides
        ],
    }

    await db.create_snapshot(
        presentation_id=pres_id,
        user_id=state["user_id"],
        conversation_id=state["conversation_id"],
        outline_json=outline_data or {},
        presentation_json=presentation_data,
    )
    _log.info("Snapshot saved for presentation %d", pres_id)

    await db.set_presentation_output(
        pres_id,
        file_path=state["file_path"],
        file_size=0,  # will be updated after actual render
        slide_count=len(slides),
    )
    await db.update_presentation_status(pres_id, "completed")
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
    builder.add_node("style_agent", style_agent_node)
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
