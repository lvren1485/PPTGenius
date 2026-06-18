"""Middleware package — SSE, Persist, Token + unified builder."""

from .persist_tool import PersistToolMiddleware
from .sse_tool import SSEToolMiddleware
from .token_tool import TokenCountingMiddleware


def build_middlewares(
    conversation_id: int,
    agent_id: str,
    ctypes: dict[str, str] | None = None,
    sub_agent_types: set[str] | None = None,
) -> tuple[list, PersistToolMiddleware | None]:
    """Build standard middlewares for an agent invocation.

    Always returns ``[SSEToolMiddleware, TokenCountingMiddleware]``.
    When ``ctypes`` is provided (master agent), prepends ``PersistToolMiddleware``
    and returns it separately so the caller can call ``flush(db)``.

    Returns (middleware_list, persist_mw_or_None).
    """
    sse = SSEToolMiddleware()
    token = TokenCountingMiddleware(conversation_id, agent_id)
    if ctypes is not None:
        persist = PersistToolMiddleware(conversation_id, ctypes, sub_agent_types or set())
        return [persist, sse, token], persist
    return [sse, token], None


__all__ = [
    "PersistToolMiddleware",
    "SSEToolMiddleware",
    "TokenCountingMiddleware",
    "build_middlewares",
]
