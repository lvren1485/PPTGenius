"""Outline agent — generator-evaluator loop for PPT outline creation.

Usage::

    from pptgenius.agent.outline import build_outline_graph, OutlineState

    graph = build_outline_graph()
    result = await graph.ainvoke(state, config={"configurable": {"db": db}})
"""

from .graph import build_outline_graph
from .state import OutlineState

__all__ = [
    "build_outline_graph",
    "OutlineState",
]
