"""Outline evaluator sub-agent — evaluates outline quality and writes suggestions."""

from __future__ import annotations

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from .prompts import build_evaluator_system_prompt

_log = get_logger("pptgenius.agent.outline.evaluator")


async def run_outline_evaluator(
    db: Database,
    conversation_id: int,
    query: str | None = None,
) -> dict:
    """Evaluate the current outline and return suggestions.

    Returns ``{overall: str, suggestions: list[str]}``.

    Phase 3: stub — Phase 4 will wire the full ReAct agent with submit_evaluation.
    """
    conv = await db.get_conversation(conversation_id)
    if conv is None or conv.current_outline_id is None:
        return {"error": "没有选中大纲"}

    outline_id = conv.current_outline_id
    outline = await db.get_outline(outline_id)
    sections = await db.get_sections_by_outline_id(outline_id)
    slides = await db.get_slides_by_outline_id(outline_id)

    _log.info(
        "evaluator stub: outline='%s' sections=%d slides=%d",
        outline.title if outline else "?", len(sections), len(slides),
    )

    _system = build_evaluator_system_prompt()

    # TODO Phase 4: create full ReAct agent with submit_evaluation tool.
    # llm, agent_id, mw = build_llm(conversation_id)
    # agent = create_agent(llm, [submit_eval_tool], system_prompt=_system, ...)

    return {
        "overall": f"大纲'{outline.title if outline else '?'}'评测待实现",
        "suggestions": [
            "评测功能将在 Phase 4 实现",
        ],
    }
