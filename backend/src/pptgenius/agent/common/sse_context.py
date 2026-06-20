"""Shared SSE writer context — set by chat API, consumed by all agents.

Replaces ``get_stream_writer()`` with an explicit context var that the chat
API controls.  This fixes the long-standing bug where LangGraph's internal
stream writer emitted events to a queue with no consumer.
"""

from __future__ import annotations

import contextvars

_sse_writer: contextvars.ContextVar = contextvars.ContextVar("sse_writer", default=None)


def get_sse_writer():
    """Return the current SSE writer callable, or a no-op fallback."""
    w = _sse_writer.get(None)
    if w is not None:
        return w
    return _noop


def set_sse_writer(writer) -> None:
    """Set the SSE writer for the current async context."""
    _sse_writer.set(writer)


def _noop(_data: dict) -> None:
    pass
