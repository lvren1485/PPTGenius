"""LangGraph graph for the outline generator-evaluator loop.

Flow
----
::

    ENTRY ──▶ generator ──▶ evaluator ──[stop?]──▶ finalize ──▶ END
                ▲                        │
                └───[continue]───────────┘

Entry always starts at generator.  Modification requests go to generator
directly (the user's feedback IS the evaluation — no need for a separate
evaluator step before generating).  After generator, evaluator always runs
to produce a score for frontend display and benchmark tracking.

The ``finalize`` node reads the finished outline from DB and packages it
into state so the frontend receives the original DB data directly.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database

from .evaluator import evaluator_node
from .generator import generator_node
from .state import OutlineState

apply_deepseek_patch()


def _get_agent_cfg():
    return get_settings().agent.outline


def _should_continue(state: OutlineState) -> Literal["generator", "finalize"]:
    """After evaluator: stop → finalize, continue → generator."""
    cfg = _get_agent_cfg()
    mode = state.get("mode", cfg.mode)
    iteration = state.get("iteration", 0)
    score = state.get("eval_score") or 0.0
    max_iter = state.get("max_iterations", cfg.max_iterations)
    pass_score = state.get("pass_score", cfg.pass_score)

    hit_max = iteration >= max_iter
    hit_score = score >= pass_score

    if mode == "max_iteration":
        return "finalize" if hit_max else "generator"
    if mode == "pass_score":
        return "finalize" if hit_score else "generator"
    # mix (default)
    return "finalize" if (hit_max or hit_score) else "generator"


async def finalize_node(state: OutlineState, config: RunnableConfig) -> dict:
    """Read the final outline from DB and package it for frontend emission."""
    db: Database = config["configurable"]["db"]
    outline_id = state.get("outline_id")
    final_data: dict | None = None

    if outline_id:
        outline = await db.get_outline(outline_id)
        if outline:
            slides = await db.get_slides_by_outline_id(outline_id)
            final_data = {
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
            }

    design_rationales = state.get("design_rationales", [])
    return {
        "final_outline_data": final_data,
        "design_rationales": design_rationales,  # ensure accumulated list is in final state
    }


def build_outline_graph() -> StateGraph:
    """Build and compile the outline generator-evaluator graph."""
    builder = StateGraph(OutlineState)

    builder.add_node("generator", generator_node)
    builder.add_node("evaluator", evaluator_node)
    builder.add_node("finalize", finalize_node)

    # Entry: always start at generator
    builder.add_edge(START, "generator")

    # Generator always goes to evaluator
    builder.add_edge("generator", "evaluator")

    # Evaluator: stop → finalize, continue → generator
    builder.add_conditional_edges("evaluator", _should_continue, {
        "generator": "generator",
        "finalize": "finalize",
    })

    builder.add_edge("finalize", END)

    return builder.compile()
