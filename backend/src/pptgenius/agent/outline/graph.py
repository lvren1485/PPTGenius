"""LangGraph graph for the outline generator-evaluator loop.

Flow
----
::

    ENTRY ──[no outline_id]──▶ generator ──▶ evaluator ──[stop?]──▶ END
        │                                    ▲        │
        └──[has outline_id]──▶ evaluator ────┘   [continue]──▶ generator

Stop modes (configured via config.yaml ``agent.outline.mode``):

- ``max_iteration`` — stop when generator has run N times
- ``pass_score`` — stop when eval_score ≥ threshold
- ``mix`` (default) — stop when either condition is met

Iteration counter increments each time the generator runs.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.infrastructure.config import get_settings

from .evaluator import evaluator_node
from .generator import generator_node
from .state import OutlineState

apply_deepseek_patch()


def _get_agent_cfg():
    return get_settings().agent.outline


def _route_entry(state: OutlineState) -> Literal["generator", "evaluator"]:
    """Entry routing.

    - No outline → generator (create new)
    - Has outline + not evaluated → evaluator first
    - Has outline + already evaluated → generator (revision)
    """
    if state.get("outline_id") is None:
        return "generator"
    if not state.get("evaluated", True):
        return "evaluator"
    return "generator"


def _should_continue(state: OutlineState) -> Literal["generator", "__end__"]:
    """After evaluator: check stop conditions based on mode."""
    cfg = _get_agent_cfg()
    mode = state.get("mode", cfg.mode)
    iteration = state.get("iteration", 0)
    score = state.get("eval_score") or 0.0
    max_iter = state.get("max_iterations", cfg.max_iterations)
    pass_score = state.get("pass_score", cfg.pass_score)

    hit_max = iteration >= max_iter
    hit_score = score >= pass_score

    if mode == "max_iteration":
        if hit_max:
            return END
    elif mode == "pass_score":
        if hit_score:
            return END
    else:  # mix (default)
        if hit_max or hit_score:
            return END

    return "generator"


def build_outline_graph() -> StateGraph:
    """Build and compile the outline generator-evaluator graph."""
    builder = StateGraph(OutlineState)

    builder.add_node("generator", generator_node)
    builder.add_node("evaluator", evaluator_node)

    # Entry routing
    builder.add_conditional_edges(START, _route_entry, {
        "generator": "generator",
        "evaluator": "evaluator",
    })

    # Generator always goes to evaluator
    builder.add_edge("generator", "evaluator")

    # Evaluator: check stop conditions
    builder.add_conditional_edges("evaluator", _should_continue, {
        "generator": "generator",
        END: END,
    })

    return builder.compile()
