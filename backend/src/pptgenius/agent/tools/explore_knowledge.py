"""Explore knowledge tool — wraps explore agent, stores result in DB."""

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
    ) -> str:
        """Explore knowledge files + web and suggest PPT outline structure in JSON.

        Call AFTER create_empty_outline.  Searches file summaries, knowledge base,
        and web for information.  Returns structured JSON with sections, each
        containing file_ids and chunk_ids citations.

        Args:
            query: User requirements or specific sections to focus on.
            file_ids: Optional specific file ids. Omit to explore all.
        """
        push_sentinel(conversation_id)
        result = await run_explore_agent(db, conversation_id, query=query, file_ids=file_ids)
        if "error" in result:
            return f"探索失败: {result['error']}"

        # Store explore result in DB
        conv = await db.get_conversation(conversation_id)
        if conv and conv.current_outline_id:
            await db.set_outline_explore_result(conv.current_outline_id, result["result"])

        return result["result"]

    return tool(_explore_knowledge)
