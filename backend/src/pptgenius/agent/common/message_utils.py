"""Shared message cleaning — strip dangling tool calls for retry safety.

When a ReAct agent hits recursion limit or crashes, the message chain may
contain orphaned AIMessage.tool_calls without matching ToolMessages,
which causes DeepSeek 400 "insufficient tool messages".
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage


def strip_dangling_tool_calls(messages: list) -> list:
    """Remove trailing messages until the chain is clean.

    A clean chain: every AIMessage.tool_calls[*].id has a matching
    ToolMessage.tool_call_id, and vice versa.

    Walks backward from the end, removing unmatched messages.
    Handles parallel tool calls (N calls in one AIMessage) — if any
    single call is unmatched, the entire AIMessage and its orphaned
    ToolMessages are removed.
    """
    cleaned = list(messages)

    while cleaned:
        last = cleaned[-1]

        if isinstance(last, AIMessage) and last.tool_calls:
            all_paired = True
            for tc in last.tool_calls:
                tc_id = tc.get("id", "")
                if not any(
                    isinstance(m, ToolMessage)
                    and getattr(m, "tool_call_id", "") == tc_id
                    for m in cleaned
                ):
                    all_paired = False
                    break
            if all_paired:
                break
            cleaned.pop()

        elif isinstance(last, ToolMessage):
            tc_id = getattr(last, "tool_call_id", "")
            if any(
                isinstance(m, AIMessage) and m.tool_calls
                and any(tc.get("id", "") == tc_id for tc in m.tool_calls)
                for m in cleaned
            ):
                break
            cleaned.pop()

        else:
            break

    return cleaned


def prepare_retry_messages(messages: list) -> list:
    """Clean messages for retry: strip dangling tool calls only."""
    return strip_dangling_tool_calls(messages)
