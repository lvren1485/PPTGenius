"""Agent layer — LangGraph agents for outline generation and PPT creation.

Usage::

    from pptgenius.agent import run_coordinator

    async for sse_event in run_coordinator(db, conversation_id, query):
        yield sse_event
"""

from .coordinator import run_coordinator
from .outline import OutlineState, build_outline_graph

__all__ = [
    "run_coordinator",
    "build_outline_graph",
    "OutlineState",
]
