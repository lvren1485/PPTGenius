"""Shared message cleaning — strip orphaned tool calls before retry.

When a ReAct agent hits recursion limit or crashes mid-tool-execution,
the message chain may contain AIMessages with tool_calls that have no
matching ToolMessage. Sending these back to the API causes a 400 error:

  "An assistant message with 'tool_calls' must be followed by tool
   messages responding to each 'tool_call_id'."

This module provides a single function to walk backwards from the end
and remove any incomplete pairs.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage


def strip_dangling_tool_calls(messages: list) -> list:
    """Remove trailing messages so no orphaned tool_calls or tool_results remain.

    A "clean" chain has the invariant: every AIMessage.tool_calls[*].id
    has a matching ToolMessage.tool_call_id, and vice versa.

    Walks backward, stripping incomplete pairs until the chain is clean.
    """
    cleaned = list(messages)

    # Keep stripping from the end until invariant holds
    while cleaned:
        last = cleaned[-1]

        if isinstance(last, AIMessage) and last.tool_calls:
            # Check that *every* tool_call in this message has a ToolMessage
            all_paired = True
            for tc in last.tool_calls:
                tc_id = tc.get("id", "")
                found = any(
                    isinstance(m, ToolMessage)
                    and getattr(m, "tool_call_id", "") == tc_id
                    for m in cleaned
                )
                if not found:
                    all_paired = False
                    break
            if all_paired:
                break  # this AIMessage is clean
            cleaned.pop()  # orphaned → remove

        elif isinstance(last, ToolMessage):
            tc_id = getattr(last, "tool_call_id", "")
            # Check that a matching AIMessage(tool_calls) exists
            found = any(
                isinstance(m, AIMessage)
                and m.tool_calls
                and any(tc.get("id", "") == tc_id for tc in m.tool_calls)
                for m in cleaned
            )
            if found:
                break  # paired → clean
            cleaned.pop()  # orphaned ToolMessage → remove

        else:
            # HumanMessage, plain AIMessage, SystemMessage → safe
            break

    return cleaned
