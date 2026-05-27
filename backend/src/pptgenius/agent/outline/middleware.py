"""Middleware for create_agent — token counting and error handling."""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime
from typing import Any

from pptgenius.infrastructure.utils import TokenCounter, get_logger

_log = get_logger("pptgenius.agent.outline.middleware")


class TokenCountingMiddleware(AgentMiddleware):
    """Accumulate token usage from every model call via after_model hook."""

    def __init__(self, conversation_id: int):
        super().__init__()
        self.conversation_id = conversation_id

    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        tc = TokenCounter.for_conversation(self.conversation_id)
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "usage_metadata") and last_msg.usage_metadata:
            tc.add(last_msg.usage_metadata)
        return None
