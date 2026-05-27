"""PPT agent graph — placeholder.

Will be implemented as a supervisor-subagent pipeline where:
- Supervisor assigns each slide to a specialized sub-agent (text/chart/table/image)
- Sub-agents generate slide content using the outline text
- A final assembly step combines all slides into a .pptx file
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.agent.ppt")


class PPTState(TypedDict):
    user_id: int
    conversation_id: int
    outline_id: int
    presentation_id: int | None
    query: str


async def _placeholder_node(state: PPTState) -> dict:
    _log.warning("PPT agent not implemented yet — outline_id=%d", state["outline_id"])
    return {"presentation_id": None}


def build_ppt_graph() -> StateGraph:
    builder = StateGraph(PPTState)
    builder.add_node("generate", _placeholder_node)
    builder.add_edge(START, "generate")
    builder.add_edge("generate", END)
    return builder.compile()
