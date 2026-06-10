"""Thread-safe registry for sub-agent token tracking.

Tool wrappers call ``push_sentinel()`` before invoking sub-agents;
sub-agents call ``push_agent()`` with their real agent_id.  The Master
calls ``pop_until_sentinel()`` to retrieve exactly the agent_ids for one
tool invocation — handles concurrent generators correctly.

Sentinel is an empty string (secrets.token_hex never produces it).
"""

_SENTINEL = ""

_agents: dict[int, list[str]] = {}  # conversation_id → [sentinel, agent_id, ...]


def push_sentinel(conversation_id: int) -> None:
    """Mark the start of a new tool invocation's agent batch."""
    _agents.setdefault(conversation_id, []).append(_SENTINEL)


def push_agent(conversation_id: int, agent_id: str) -> None:
    """Push a sub-agent's id onto the stack."""
    _agents.setdefault(conversation_id, []).append(agent_id)


def pop_until_sentinel(conversation_id: int) -> list[str]:
    """Pop agent_ids from the top of the stack until the sentinel.

    Returns the agent_ids (in pop order, youngest first).  Sentinel is removed.
    """
    stack = _agents.get(conversation_id)
    if not stack:
        return []
    ids: list[str] = []
    while stack:
        v = stack.pop()
        if v == _SENTINEL:
            break
        ids.append(v)
    if not stack:
        _agents.pop(conversation_id, None)
    return ids
