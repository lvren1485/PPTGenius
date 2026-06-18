"""Tests for Phase 1 — TokenCounter extension, TokenCountingMiddleware, model_builder."""

import pytest

from pptgenius.infrastructure.utils.token_counter import TokenCounter


class TestTokenCounterDualLayer:
    """Agent-level token counters with cleanup."""

    def test_for_agent_creates_counter(self):
        tc = TokenCounter.for_agent("agent_abc")
        assert tc is not None
        assert tc.call_count == 0

    def test_for_agent_returns_same_counter(self):
        tc1 = TokenCounter.for_agent("agent_xyz")
        tc2 = TokenCounter.for_agent("agent_xyz")
        assert tc1 is tc2

    def test_for_agent_accumulates(self):
        tc = TokenCounter.for_agent("agent_test")
        tc.add({"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})
        assert tc.prompt_tokens == 100
        assert tc.completion_tokens == 50
        assert tc.total_tokens == 150

    def test_get_agent_returns_none_for_unknown(self):
        assert TokenCounter.get_agent("nonexistent") is None

    def test_remove_agent(self):
        TokenCounter.for_agent("temp_agent").add({"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
        TokenCounter.remove_agent("temp_agent")
        assert TokenCounter.get_agent("temp_agent") is None

    def test_snapshot_after_add(self):
        tc = TokenCounter.for_agent("snap_agent")
        tc.add({
            "input_tokens": 200, "output_tokens": 100, "total_tokens": 300,
            "prompt_cache_hit_tokens": 50, "prompt_cache_miss_tokens": 150,
            "output_token_details": {"reasoning_tokens": 30},
        })
        snap = tc.snapshot()
        assert snap["prompt_tokens"] == 200
        assert snap["completion_tokens"] == 100
        assert snap["call_count"] == 1


class TestTokenCountingMiddleware:
    """Validate middleware structure."""

    def test_middleware_creation(self):
        from pptgenius.agent.common.middleware.token_tool import TokenCountingMiddleware
        mw = TokenCountingMiddleware(conversation_id=1, agent_id="test_agent")
        assert mw.conversation_id == 1
        assert mw.agent_id == "test_agent"


class TestSetMessageCost:
    @pytest.mark.asyncio
    async def test_set_message_cost(self, db):
        from pptgenius.infrastructure.db.database import Database
        d = Database(db)
        u = await d.create_user("cost_user")
        conv = await d.create_conversation(u.id)
        msg = await d.create_message(conv.id, "tool", "{}", content_type="toolresult_test")
        await d.set_message_cost(msg.id, {"input": 500, "output": 200, "total": 700}, 0.001)
        fetched = (await d.get_messages_by_conversation(conv.id))[0]
        assert fetched.token_cost_json == {"input": 500, "output": 200, "total": 700}
        assert fetched.estimated_cost == 0.001
        # estimated_cost should have accumulated to conversation too
        conv_fetched = await d.get_conversation(conv.id)
        assert conv_fetched.estimated_cost > 0


class TestModelBuilder:
    """Validate create_llm + build_middlewares."""

    def test_create_llm_returns_pair(self):
        from pptgenius.infrastructure.llm import create_llm
        llm, agent_id = create_llm(conversation_id=1)
        assert llm is not None
        assert isinstance(agent_id, str)
        assert len(agent_id) == 8  # token_hex(4) = 8 hex chars

    def test_build_middlewares_sub_agent(self):
        from pptgenius.infrastructure.llm import create_llm
        from pptgenius.agent.common.middleware import build_middlewares
        _, agent_id = create_llm(conversation_id=1)
        mws, persist = build_middlewares(1, agent_id)
        assert len(mws) == 2  # SSE + Token
        assert persist is None

    def test_build_middlewares_master(self):
        from pptgenius.infrastructure.llm import create_llm
        from pptgenius.agent.common.middleware import build_middlewares
        _, agent_id = create_llm(conversation_id=1)
        mws, persist = build_middlewares(1, agent_id, ctypes={"t": "c"}, sub_agent_types={"x"})
        assert len(mws) == 3  # Persist + SSE + Token
        assert persist is not None

    def test_create_llm_agent_id_unique(self):
        from pptgenius.infrastructure.llm import create_llm
        ids = {create_llm(1)[1] for _ in range(10)}
        assert len(ids) == 10

    def test_create_llm_token_mw_ids(self):
        from pptgenius.infrastructure.llm import create_llm
        from pptgenius.agent.common.middleware import build_middlewares
        _, agent_id = create_llm(42)
        mws, _ = build_middlewares(42, agent_id)
        token_mw = [m for m in mws if type(m).__name__ == "TokenCountingMiddleware"][0]
        assert token_mw.conversation_id == 42
        assert token_mw.agent_id == agent_id
