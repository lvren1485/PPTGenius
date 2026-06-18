"""Explore knowledge tool — thin wrapper delegating to agent/outline/explore.py."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database

from ..common.agent_registry import push_sentinel
from ..outline.explore import run_explore_agent


def make_explore_knowledge(db: Database, conversation_id: int) -> Callable:

    async def _explore_knowledge(
        query: str | None = None,
        file_ids: list[int] | None = None,
    ) -> dict:
        """Explore knowledge files and suggest PPT outline structure.

        Call BEFORE write_outline_structure. Reads file summaries, searches
        knowledge base and web, returns outline structure suggestions.

        Args:
            query: Optional user requirements.
            file_ids: Optional specific file ids to explore. Omit to explore all.
        """
        push_sentinel(conversation_id)
        result = await run_explore_agent(db, conversation_id, query=query, file_ids=file_ids)
        if "error" in result:
            return {"result": result["error"], "status": "error"}
        return result

    return tool(_explore_knowledge)
