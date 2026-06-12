"""Shared message cleaning — strip orphaned tool calls, sanitize content, compress results.

When a ReAct agent hits recursion limit or crashes, the message chain may contain:
- orphaned tool_calls → 400 "insufficient tool messages"
- unicode control chars / invalid surrogates → 400 encoding errors
- huge tool results → token limits / 400

Events: strip → sanitize → compress (in that order).
"""

from __future__ import annotations

import re
import unicodedata

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

_TOOL_RESULT_MAX_CHARS = 500

# Unicode categories to strip (control chars except common whitespace)
_CONTROL_CHARS = "".join(
    chr(c) for c in range(0x00, 0x20) if chr(c) not in ("\t", "\n", "\r")
) + "".join(chr(c) for c in range(0x7F, 0xA0))  # DEL + C1 controls
_CONTROL_RE = re.compile("[" + _CONTROL_CHARS + "]")
_SURROGATE_RE = re.compile("[\uD800-\uDFFF]")


def _sanitize_str(text: str) -> str:
    """Remove or replace characters likely to break JSON/API transport."""
    # Strip control chars (keep \t \n \r)
    text = _CONTROL_RE.sub("", text)
    # Strip surrogates (invalid in JSON)
    text = _SURROGATE_RE.sub("", text)
    # Normalize to NFC (composed form, most compatible)
    text = unicodedata.normalize("NFC", text)
    return text


def _sanitize_message(msg):
    """Sanitize string content of any message type."""
    if hasattr(msg, "content") and isinstance(msg.content, str):
        cleaned = _sanitize_str(msg.content)
        if isinstance(msg, AIMessage):
            return AIMessage(content=cleaned)
        elif isinstance(msg, HumanMessage):
            return HumanMessage(content=cleaned)
        elif isinstance(msg, SystemMessage):
            return SystemMessage(content=cleaned)
        elif isinstance(msg, ToolMessage):
            return ToolMessage(
                content=cleaned,
                tool_call_id=getattr(msg, "tool_call_id", ""),
                name=getattr(msg, "name", None),
            )
    return msg


def sanitize_messages(messages: list) -> list:
    """Strip dangerous characters from ALL messages' string content."""
    return [_sanitize_message(m) for m in messages]


def strip_dangling_tool_calls(messages: list) -> list:
    """Remove trailing messages so no orphaned tool_calls or tool_results remain.

    A "clean" chain has the invariant: every AIMessage.tool_calls[*].id
    has a matching ToolMessage.tool_call_id, and vice versa.

    Walks backward, stripping incomplete pairs until the chain is clean.
    """
    cleaned = list(messages)

    while cleaned:
        last = cleaned[-1]

        if isinstance(last, AIMessage) and last.tool_calls:
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
                break
            cleaned.pop()

        elif isinstance(last, ToolMessage):
            tc_id = getattr(last, "tool_call_id", "")
            found = any(
                isinstance(m, AIMessage)
                and m.tool_calls
                and any(tc.get("id", "") == tc_id for tc in m.tool_calls)
                for m in cleaned
            )
            if found:
                break
            cleaned.pop()

        else:
            break

    return cleaned


def compress_tool_results(messages: list, max_chars: int = _TOOL_RESULT_MAX_CHARS) -> list:
    """Truncate every ToolMessage's content to *max_chars* chars.

    Keeps the full message chain intact (model knows what tools were called
    and what they returned), but drops the bulk of large results so retry
    doesn't hit token limits or cause API errors.

    Only modifies ToolMessage.content — AIMessage, HumanMessage etc. untouched.
    """
    compressed = []
    for m in messages:
        if isinstance(m, ToolMessage) and hasattr(m, "content") and m.content:
            content = str(m.content)
            if len(content) > max_chars:
                truncated = content[:max_chars] + f"\n...[截断, 原{len(content)}字符]"
                compressed.append(ToolMessage(
                    content=truncated,
                    tool_call_id=getattr(m, "tool_call_id", ""),
                    name=getattr(m, "name", None),
                ))
            else:
                compressed.append(m)
        else:
            compressed.append(m)
    return compressed


def prepare_retry_messages(messages: list) -> list:
    """Full retry pipeline: strip → sanitize → compress.  Safe to call on any messages."""
    clean = strip_dangling_tool_calls(messages)
    clean = sanitize_messages(clean)
    clean = compress_tool_results(clean)
    return clean
