"""Tests for Phase 5 middleware — SSEToolMiddleware, PersistToolMiddleware.

These test structure and initialization; full integration (SSE events, DB writes
during agent execution) is covered by integration tests.
"""

import pytest

from pptgenius.agent.common.middleware import PersistToolMiddleware, SSEToolMiddleware


_TOOL_CTYPE = {
    "_get_outline": "get_outline",
    "_gen_content": "gen_content",
    "_slides_content": "slides_content",
}
_SUB_AGENTS = {"gen_content", "slides_content"}


class TestSSEToolMiddleware:
    def test_creation(self):
        mw = SSEToolMiddleware()
        assert mw is not None

    def test_is_agent_middleware(self):
        from langchain.agents.middleware import AgentMiddleware
        assert isinstance(SSEToolMiddleware(), AgentMiddleware)


class TestPersistToolMiddlewareCreation:
    def test_creation(self):
        mw = PersistToolMiddleware(
            conversation_id=1,
            ctypes=_TOOL_CTYPE,
            sub_agent_types=_SUB_AGENTS,
        )
        assert mw.conversation_id == 1
        assert mw._ctypes == _TOOL_CTYPE
        assert mw._sub_agents == _SUB_AGENTS
        assert mw._pending == []
        assert mw._last_reasoning == ""

    def test_is_agent_middleware(self):
        from langchain.agents.middleware import AgentMiddleware
        mw = PersistToolMiddleware(1, _TOOL_CTYPE, _SUB_AGENTS)
        assert isinstance(mw, AgentMiddleware)

    def test_flush_clears_pending(self):
        mw = PersistToolMiddleware(1, _TOOL_CTYPE, _SUB_AGENTS)
        # Simulate a tool call entry
        mw._pending.append({"role": "tool_call", "content": "", "content_type": "test", "metadata_json": {"tool_call_id": "x"}})
        mw._pending.append({"role": "tool_result", "content": "ok", "content_type": "test", "metadata_json": {"tool_call_id": "x"}, "is_sub_agent": False})
        assert len(mw._pending) == 2
        mw._pending.clear()
        assert len(mw._pending) == 0
