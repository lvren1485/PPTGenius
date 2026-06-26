"""Shared message cleaning — strip dangling tool calls for retry safety.

When a ReAct agent hits recursion limit or crashes, the message chain may
contain orphaned AIMessage.tool_calls without matching ToolMessages,
which causes DeepSeek 400 "insufficient tool messages".
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage


def strip_dangling_tool_calls(messages: list) -> list:
    """Remove AIMessages with unpaired tool_calls anywhere in the chain.

    Full scan — not limited to trailing messages.  A tool_call is
    unpaired if no ToolMessage with a matching tool_call_id exists
    ANYWHERE in the list.  When an AIMessage has at least one unpaired
    call, the entire AIMessage and ALL its paired ToolMessages are
    removed.
    """
    # Collect all tool_call_ids that have ToolMessages
    paired_ids: set[str] = set()
    for m in messages:
        if isinstance(m, ToolMessage):
            tc_id = getattr(m, "tool_call_id", "")
            if tc_id:
                paired_ids.add(tc_id)

    # Identify AIMessages with at least one unpaired tool_call
    bad_ids: set[str] = set()
    bad_ai_indices: set[int] = set()
    for i, m in enumerate(messages):
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                tc_id = tc.get("id", "")
                if tc_id and tc_id not in paired_ids:
                    bad_ids.add(tc_id)
            if any(tc.get("id", "") in bad_ids for tc in m.tool_calls):
                # Mark the paired call ids of this message for removal too
                for tc in m.tool_calls:
                    tc_id = tc.get("id", "")
                    if tc_id:
                        bad_ids.add(tc_id)
                bad_ai_indices.add(i)

    if not bad_ids:
        return list(messages)

    return [
        m for m in messages
        if not (
            (isinstance(m, AIMessage) and any(
                tc.get("id", "") in bad_ids for tc in (m.tool_calls or [])
            ))
            or (isinstance(m, ToolMessage)
                and getattr(m, "tool_call_id", "") in bad_ids)
        )
    ]


def prepare_retry_messages(messages: list) -> list:
    """Clean messages for retry: strip dangling tool calls only."""
    return strip_dangling_tool_calls(messages)
