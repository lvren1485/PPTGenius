"""Outline evaluate tool — thin wrapper delegating to agent/outline/evaluator.py."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database

from ..common.agent_registry import push_sentinel
from ..common.tool_sse_wrapper import wrap_tool_with_sse
from ..outline.evaluator import run_outline_evaluator


def make_outline_evaluate(db: Database, conversation_id: int) -> Callable:
    """Single tool: evaluate the current outline quality."""

    async def _outline_evaluate(query: str | None = None) -> dict:
        """Evaluate outline quality and return suggestions.

        Call after all sections are generated. Returns overall assessment and
        a list of actionable improvement suggestions.

        Args:
            query: Optional specific evaluation criteria from the user.
        """
        push_sentinel(conversation_id)
        return await run_outline_evaluator(db, conversation_id, query=query)

    return tool(wrap_tool_with_sse(_outline_evaluate))
