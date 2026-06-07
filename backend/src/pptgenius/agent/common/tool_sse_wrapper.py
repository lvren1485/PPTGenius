"""Tool SSE wrapper — emits tool_start / tool_end events around every Master tool call."""
# TODO: UNTEST WITH FULL FUNCTIONALITY, needed for test with langchain, stream writer cannot work in static test environment. 

from __future__ import annotations

import functools
from typing import Any, Callable

from langgraph.config import get_stream_writer


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


def wrap_tool_with_sse(fn: Callable) -> Callable:
    """Wrap an async tool function to emit tool_start/tool_end SSE events.

    Usage::

        tool_func = wrap_tool_with_sse(tool_func)
        # The returned function will emit SSE before/after each call.
    """

    @functools.wraps(fn)
    async def _wrapped(**kwargs: Any) -> Any:
        writer = _get_writer()
        tool_name = getattr(fn, "__name__", "unknown")
        writer({"type": "tool_start", "tool": tool_name, "args": _safe_args(kwargs)})
        try:
            result = await fn(**kwargs)
        except Exception as exc:
            writer({"type": "tool_error", "tool": tool_name, "error": str(exc)})
            raise
        writer({"type": "tool_end", "tool": tool_name,
                "result_len": len(str(result)) if result else 0})
        return result

    return _wrapped


def _safe_args(kwargs: dict) -> dict:
    """Truncate large arg values for SSE display."""
    safe = {}
    for k, v in kwargs.items():
        s = str(v)
        if len(s) > 100:
            safe[k] = s[:100] + "..."
        else:
            safe[k] = v
    return safe
