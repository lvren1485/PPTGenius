"""Persist tool middleware — collects tool_call/tool_result data during agent
execution and provides ``flush()`` for batch persistence after the agent completes.

Gradual persistence (one DB write per tool call) is deferred to a future
LangChain version that stabilises async middleware hooks.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.messages import AIMessage, ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import TokenCounter

from ..agent_registry import pop_until_sentinel


class PersistToolMiddleware(AgentMiddleware):
    """Collect every tool_call + tool_result pair during agent execution.

    Call ``flush(db)`` after ``agent.ainvoke()`` returns to persist all
    collected messages to the database (replaces ``_persist_tool_messages``).
    """

    def __init__(
        self,
        conversation_id: int,
        ctypes: dict[str, str],
        sub_agent_types: set[str],
    ):
        super().__init__()
        self.conversation_id = conversation_id
        self._ctypes = ctypes
        self._sub_agents = sub_agent_types
        self._pending: list[dict] = []      # collected tool_call/tool_result entries
        self._last_reasoning: str = ""       # cached from after_model

    # ── hooks ──────────────────────────────────────────────────────────

    def after_model(
        self, state: AgentState, runtime: Runtime
    ) -> dict | None:
        """Cache reasoning_content from the latest AIMessage."""
        msgs = state.get("messages", [])
        if msgs:
            last = msgs[-1]
            if isinstance(last, AIMessage):
                self._last_reasoning = (
                    last.additional_kwargs.get("reasoning_content", "")
                )
        return None

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        tc_name = request.tool_call["name"]
        tc_args = request.tool_call["args"]
        tc_id = request.tool_call["id"]
        ctype = self._ctypes.get(tc_name, "tool_call")

        # ① Collect tool_call entry
        meta: dict = {
            "tool_name": tc_name,
            "args": tc_args,
            "tool_call_id": tc_id,
        }
        if self._last_reasoning:
            meta["reasoning_content"] = self._last_reasoning
        self._pending.append({
            "role": "tool_call",
            "content": tc_args.get("query", "") or "",
            "content_type": ctype,
            "metadata_json": meta,
        })

        # ② Execute the tool
        result = handler(request)

        # ③ Collect tool_result entry
        content = str(result.content) if hasattr(result, "content") else str(result)
        result_meta = {
            "tool_name": tc_name,
            "tool_call_id": tc_id,
        }
        self._pending.append({
            "role": "tool_result",
            "content": content,
            "content_type": ctype,
            "metadata_json": result_meta,
            "is_sub_agent": ctype in self._sub_agents,
        })

        return result

    # ── persistence — called after ainvoke ────────────────────────────

    async def flush(self, db: Database) -> None:
        """Persist all collected tool_call/tool_result entries.

        Deduplicates by tool_call_id so messages from earlier turns
        (already in DB) are not duplicated.
        """
        existing = await db.get_messages_by_conversation(self.conversation_id)
        seen_ids: set[str] = set()
        for r in existing:
            meta = r.metadata_json or {}
            tc_id = meta.get("tool_call_id", "")
            if tc_id:
                seen_ids.add(tc_id)

        for entry in self._pending:
            role = entry["role"]

            if role == "tool_call":
                tc_id = entry["metadata_json"]["tool_call_id"]
                if tc_id in seen_ids:
                    continue
                await db.create_message(
                    conversation_id=self.conversation_id,
                    role="tool_call",
                    content=entry["content"],
                    content_type=entry["content_type"],
                    metadata_json=entry["metadata_json"],
                )

            elif role == "tool_result":
                tc_id = entry["metadata_json"]["tool_call_id"]
                if tc_id in seen_ids:
                    continue
                msg = await db.create_message(
                    conversation_id=self.conversation_id,
                    role="tool_result",
                    content=entry["content"],
                    content_type=entry["content_type"],
                    metadata_json=entry["metadata_json"],
                )

                # Flush sub-agent token counters
                if entry.get("is_sub_agent"):
                    agent_ids = pop_until_sentinel(self.conversation_id)
                    if agent_ids:
                        summed: dict = {}
                        total_cost = 0.0
                        for aid in agent_ids:
                            tc = TokenCounter.get_agent(aid)
                            if tc:
                                for k, v in tc.to_json().items():
                                    summed[k] = summed.get(k, 0) + v
                                total_cost += tc.snapshot()["estimated_cost_cny"]
                        await db.set_message_cost(msg.id,
                            token_cost_json=summed,
                            estimated_cost=total_cost,
                        )

        self._pending.clear()
