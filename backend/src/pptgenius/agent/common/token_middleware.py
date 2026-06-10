"""Token-counting middleware — accumulates token usage per conversation + per agent."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

from pptgenius.infrastructure.utils import TokenCounter


class TokenCountingMiddleware(AgentMiddleware):
    """Accumulate token usage from every model call via after_model hook.

    Writes to:
    - TokenCounter.for_conversation(conversation_id)
    - TokenCounter.for_agent(agent_id)
    - Optional async persist callback for DB message row.
    """

    def __init__(
        self,
        conversation_id: int,
        agent_id: str,
        on_tokens: Callable[[dict], Awaitable[None]] | None = None,
    ):
        super().__init__()
        self.conversation_id = conversation_id
        self.agent_id = agent_id
        self.on_tokens = on_tokens

    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        last_msg = state["messages"][-1]
        usage = None
        if hasattr(last_msg, "usage_metadata") and last_msg.usage_metadata:
            usage = last_msg.usage_metadata

        if usage:
            tc_conv = TokenCounter.for_conversation(self.conversation_id)
            tc_agent = TokenCounter.for_agent(self.agent_id)
            tc_conv.add(usage)
            tc_agent.add(usage)

            if self.on_tokens is not None:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.on_tokens(usage))
                except RuntimeError:
                    pass

        return None




