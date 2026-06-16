"""Explore knowledge tool — thin wrapper delegating to agent/outline/knowledge.py."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database

from ..common.agent_registry import push_sentinel
from ..outline.knowledge import run_knowledge_agent


def make_explore_knowledge(db: Database, conversation_id: int) -> Callable:

    async def _explore_knowledge(
        query: str | None = None,
        file_ids: list[int] | None = None,
    ) -> dict:
        """Explore knowledge files and suggest PPT outline structure.

        Call BEFORE write_outline_structure. Reads files, understands content,
        and returns a natural-language exploration result with outline suggestions.

        Args:
            query: Optional user requirements.
            file_ids: Optional specific file ids to explore. Omit to explore all.
        """
        push_sentinel(conversation_id)
        return await run_knowledge_agent(db, conversation_id, query=query, file_ids=file_ids)

    return tool(_explore_knowledge)
