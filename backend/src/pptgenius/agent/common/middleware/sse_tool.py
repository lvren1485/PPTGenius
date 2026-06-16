"""SSE tool middleware — emits tool_start / tool_end events around every tool call.

Replaces ``wrap_tool_with_sse`` decorator.  Registered once in create_agent,
applies to ALL tools automatically.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.config import get_stream_writer
from langgraph.types import Command


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


def _safe_args(kwargs: dict) -> dict:
    safe = {}
    for k, v in kwargs.items():
        s = str(v)
        safe[k] = s[:100] + "..." if len(s) > 100 else v
    return safe


class SSEToolMiddleware(AgentMiddleware):
    """Emit tool_start / tool_end / tool_error SSE for every tool invocation."""

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        writer = _get_writer()
        tc_name = request.tool_call["name"]
        tc_args = request.tool_call["args"]

        writer({"type": "tool_start", "tool": tc_name, "args": _safe_args(tc_args)})
        try:
            result = handler(request)
        except Exception as exc:
            writer({"type": "tool_error", "tool": tc_name, "error": str(exc)})
            raise
        result_len = len(str(result.content)) if hasattr(result, "content") else 0
        writer({"type": "tool_end", "tool": tc_name, "result_len": result_len})
        return result
