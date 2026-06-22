"""SSE tool middleware — emits tool_start / tool_end events around every tool call.

Replaces ``wrap_tool_with_sse`` decorator.  Registered once in create_agent,
applies to ALL tools automatically.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command

from ..sse_context import get_sse_writer


def _safe_args(kwargs: dict) -> dict:
    safe = {}
    for k, v in kwargs.items():
        s = str(v)
        safe[k] = s[:100] + "..." if len(s) > 100 else v
    return safe


class SSEToolMiddleware(AgentMiddleware):
    """Emit tool_start / tool_end / tool_error SSE for every tool invocation."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        writer = get_sse_writer()
        tc_name = request.tool_call["name"]
        tc_args = request.tool_call["args"]

        writer({"type": "tool_start", "tool": tc_name, "args": _safe_args(tc_args)})
        try:
            result = await handler(request)
        except Exception as exc:
            writer({"type": "tool_error", "tool": tc_name, "error": str(exc)})
            raise
        content = str(result.content) if hasattr(result, "content") else ""
        writer({
            "type": "tool_end",
            "tool": tc_name,
            "result": content[:500],
            "result_len": len(content),
        })
        return result
