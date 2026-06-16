"""ppt_style tool — thin wrapper delegating to agent/ppt/style_agent.py."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database

from ..common.agent_registry import push_sentinel
from ..ppt.style_agent import run_style_agent


def make_ppt_style(db: Database, conversation_id: int) -> Callable:

    async def _ppt_style(query: str | None = None) -> str:
        """Select a visual style (color scheme + background) for the presentation.

        Call after outline content is confirmed. The agent browses available styles,
        considers the outline topic and audience, and selects the best match.

        Args:
            query: Optional user style requirements, e.g. "换成科技深色风格".
        """
        push_sentinel(conversation_id)
        result = await run_style_agent(db, conversation_id)
        if "error" in result:
            return result["error"]
        return (
            f"已选择样式:'{result.get('style_label','')}'(id={result.get('style_id')})。"
        )

    return tool(_ppt_style)
