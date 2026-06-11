"""Token-counting middleware — accumulates token usage per conversation + per agent."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

from pptgenius.infrastructure.utils import TokenCounter


class TokenCountingMiddleware(AgentMiddleware):
    """Accumulate token usage from every model call via after_model hook.

    Writes to both the conversation-level counter (for SSE summary) and
    the per-agent counter (for per-message persistence).
    """

    def __init__(self, conversation_id: int, agent_id: str):
        super().__init__()
        self.conversation_id = conversation_id
        self.agent_id = agent_id

    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        last_msg = state["messages"][-1]
        usage = None
        if hasattr(last_msg, "usage_metadata") and last_msg.usage_metadata:
            usage = last_msg.usage_metadata

        if usage:
            TokenCounter.for_conversation(self.conversation_id).add(usage)
            TokenCounter.for_agent(self.agent_id).add(usage)

        return None
