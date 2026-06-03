"""PPT agent graph — two-phase pipeline with parallel slide dispatch.

Phase 1: StyleAgent selects color_scheme + layout
Phase 2: Dispatcher fans out per-slide super_freedom agents (parallel, semaphore-bounded)
Assembly: collect agent outputs → render .pptx → snapshot
"""

from __future__ import annotations

import os

from langgraph.graph import END, START, StateGraph

from pptgenius.infrastructure.utils import get_logger

from .phase1_style import style_agent_node
from .phase2_sub_agent.dispatcher import dispatcher_node
from .state import PPTState

_log = get_logger("pptgenius.agent.ppt")


# ── nodes ─────────────────────────────────────────────────────────────────────


async def _create_presentation_node(state: PPTState, config) -> dict:
    """Create presentation record + ALL presentation_slides upfront from outline."""
    from pptgenius.infrastructure.db import Database
    from pptgenius.agent.ppt.common.layout_resolver import select_layout

    db: Database = config["configurable"]["db"]

    presentation_id = state.get("presentation_id")
    if presentation_id is None:
        pres = await db.create_presentation(
            user_id=state["user_id"],
            conversation_id=state["conversation_id"],
            outline_id=state["outline_id"],
        )
        presentation_id = pres.id

    # Load outline slides (ORM objects with .id)
    outline_slide_objs = await db.get_slides_by_outline_id(state["outline_id"])
    outline_slides = [
        {
            "slide_index": s.slide_index,
            "outline_slide_id": s.id,
            "title": s.title,
            "content_json": s.content_json,
            "layout_type": s.layout_type,
            "has_image": s.has_image,
            "has_chart": s.has_chart,
            "notes": s.notes,
        }
        for s in outline_slide_objs
    ]

    # Load template layouts for dispatcher/supervisor
    selected_layouts = state.get("selected_layouts", {})
    if not selected_layouts:
        templates = await db.list_active_templates()
        if templates:
            selected_layouts = templates[0].layouts_json or {}

    # Create ALL presentation_slides upfront in a single batch commit
    existing_slides = await db.get_slides_by_presentation_id(presentation_id)
    existing_indices = {s.slide_index for s in existing_slides}
    new_slides = []
    for s in outline_slide_objs:
        if s.slide_index not in existing_indices:
            new_slides.append({
                "presentation_id": presentation_id,
                "slide_index": s.slide_index,
                "layout_name": select_layout({
                    "layout_type": s.layout_type or "content",
                }),
                "outline_slide_id": s.id,
                "color_scheme_id": state.get("color_scheme_id"),
                "template_id": state.get("template_id"),
            })
    if new_slides:
        await db.create_presentation_slides_batch(new_slides)

    _log.info("Created presentation %d with %d slides upfront",
              presentation_id, len(outline_slides))

    return {
        "presentation_id": presentation_id,
        "outline_slides": outline_slides,
        "total_slides": len(outline_slides),
        "current_slide_index": 0,
        "selected_layouts": selected_layouts,
    }


async def _assembly_node(state: PPTState, config) -> dict:
    """Assembly: merge layout + agent outputs → validate → render .pptx → snapshot."""
    from pptgenius.infrastructure.db import Database

    db: Database = config["configurable"]["db"]
    pres_id = state["presentation_id"]
    _log.info("Assembly: presentation_id=%d", pres_id)

    pres = await db.get_presentation(pres_id)
    outline = await db.get_outline(state["outline_id"])
    slides = await db.get_slides_by_presentation_id(pres_id)

    # ── build instruction JSON for PPT generator ──
    ppt_slides: list[dict] = []
    for s in sorted(slides, key=lambda x: x.slide_index):
        outputs = s.agent_outputs or {}
        sf = outputs.get("super_freedom", {})
        ppt_slides.append({
            "layout": "blank",
            "background": sf.get("background"),
            "notes": sf.get("notes", ""),
            "elements": sf.get("elements", []),
        })
        _log.debug('  Slide %d: super_freedom — %d elements', s.slide_index, len(sf.get("elements", [])))

    instruction = {
        "meta": {"slide_width": 13.333, "slide_height": 7.5, "language": "zh"},
        "slides": ppt_slides,
    }

    # ── render .pptx ──
    from pptgenius.infrastructure.ppt_engine.generator import generate_ppt
    from pptgenius.infrastructure.workspace.manager import WorkspaceManager

    wm = WorkspaceManager()
    output_dir = wm.get_output_dir(state["conversation_id"])
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{pres_id}.pptx"
    file_path = os.path.join(output_dir, filename)

    result = await generate_ppt(instruction, file_path)

    file_size = 0
    if result.get("ok"):
        file_size = result.get("file_size", 0)
        _log.info("PPTX saved: %s (%d bytes)", file_path, file_size)
    else:
        _log.error("PPTX generation failed: %s", result.get("errors", "unknown"))

    # ── snapshot ──
    outline_data = None
    if outline:
        outline_slides = await db.get_slides_by_outline_id(outline.id)
        outline_data = {
            "id": outline.id, "title": outline.title, "version": outline.version,
            "slide_count": outline.slide_count, "eval_score": outline.eval_score,
            "slides": [
                {"slide_index": ol_s.slide_index, "title": ol_s.title,
                 "layout_type": ol_s.layout_type, "content_json": ol_s.content_json}
                for ol_s in outline_slides
            ],
        }
    presentation_data = {
        "id": pres.id if pres else pres_id,
        "slide_count": len(slides),
        "color_scheme_id": state.get("color_scheme_id"),
        "template_id": state.get("template_id"),
        "slides": [
            {"slide_index": ps.slide_index, "layout_name": ps.layout_name,
             "agent_outputs": ps.agent_outputs, "status": ps.status}
            for ps in slides
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
        file_path=file_path,
        file_size=file_size,
        slide_count=len(slides),
    )
    await db.update_presentation_status(pres_id, "completed")
    return {}


# ── routing ──


def _route_style(state: PPTState) -> str:
    """Skip Phase 1 if style is already selected (modify without style change)."""
    if state.get("color_scheme_id") and state.get("template_id"):
        _log.info("Style already selected, skipping Phase 1")
        return "dispatcher"
    return "style_agent"


# ── graph builder ──


def build_ppt_graph() -> StateGraph:
    """Build the PPT agent StateGraph.

    Flow: create_presentation → style_agent → dispatcher → assembly
    """
    builder = StateGraph(PPTState)

    builder.add_node("create_presentation", _create_presentation_node)
    builder.add_node("style_agent", style_agent_node)
    builder.add_node("dispatcher", dispatcher_node)
    builder.add_node("assembly", _assembly_node)

    # Edges — one-shot pipeline, no loopback
    builder.add_edge(START, "create_presentation")
    builder.add_conditional_edges("create_presentation", _route_style, {
        "style_agent": "style_agent",
        "dispatcher": "dispatcher",
    })
    builder.add_edge("style_agent", "dispatcher")
    builder.add_edge("dispatcher", "assembly")
    builder.add_edge("assembly", END)

    return builder.compile()
