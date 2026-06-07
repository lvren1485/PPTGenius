"""Tests for Phase 1 — TokenCounter extension, TokenCountingMiddleware, model_builder."""

import pytest

from pptgenius.infrastructure.utils.token_counter import TokenCounter


class TestTokenCounterDualLayer:
    """New: _agent_counters + for_agent + get_cost dual interface."""

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

    def test_get_cost_dual_interface(self):
        # int → conversation
        tc_conv = TokenCounter.for_conversation(9999)
        assert TokenCounter.get_cost(9999) is tc_conv
        # str → agent
        tc_agent = TokenCounter.for_agent("dual_test")
        assert TokenCounter.get_cost("dual_test") is tc_agent

    def test_get_cost_returns_none(self):
        assert TokenCounter.get_cost(88888) is None
        assert TokenCounter.get_cost("no_such_agent") is None

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
    """Validate middleware structure and hook signature."""

    def test_middleware_creation(self):
        from pptgenius.agent.common.token_middleware import TokenCountingMiddleware
        mw = TokenCountingMiddleware(
            conversation_id=1,
            agent_id="test_agent",
        )
        assert mw.conversation_id == 1
        assert mw.agent_id == "test_agent"
        assert mw.on_tokens is None

    def test_middleware_with_callback(self):
        from pptgenius.agent.common.token_middleware import TokenCountingMiddleware
        called = []

        async def on_tokens(usage):
            called.append(usage)

        mw = TokenCountingMiddleware(1, "test", on_tokens=on_tokens)
        assert mw.on_tokens is not None


class TestPersistAgentTokens:
    @pytest.mark.asyncio
    async def test_persist_writes_to_message(self, db):
        from pptgenius.infrastructure.db.database import Database
        from pptgenius.agent.common.token_middleware import persist_agent_tokens
        d = Database(db)
        u = await d.create_user("pat_user")
        conv = await d.create_conversation(u.id)
        msg = await d.create_message(conv.id, "tool", "{}", content_type="toolresult_test")
        agent_id = "pat_agent_1"
        TokenCounter.for_agent(agent_id).add({
            "input_tokens": 300, "output_tokens": 150, "total_tokens": 450,
        })
        await persist_agent_tokens(d, msg.id, agent_id)
        fetched = (await d.get_messages_by_conversation(conv.id))[0]
        assert fetched.token_cost_json["total_tokens"] == 450
        assert fetched.estimated_cost > 0

    @pytest.mark.asyncio
    async def test_persist_unknown_agent_does_nothing(self, db):
        from pptgenius.infrastructure.db.database import Database
        from pptgenius.agent.common.token_middleware import persist_agent_tokens
        d = Database(db)
        u = await d.create_user("pat2_user")
        conv = await d.create_conversation(u.id)
        msg = await d.create_message(conv.id, "tool", "{}")
        await persist_agent_tokens(d, msg.id, "nonexistent_agent")
        fetched = (await d.get_messages_by_conversation(conv.id))[0]
        assert fetched.token_cost_json is None


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
    """Validate build_llm returns expected triple."""

    def test_build_llm_returns_triple(self):
        from pptgenius.agent.common.model_builder import build_llm
        llm, agent_id, middleware = build_llm(conversation_id=1)
        assert llm is not None
        assert isinstance(agent_id, str)
        assert len(agent_id) == 8  # token_hex(4) = 8 hex chars
        assert middleware is not None

    def test_build_llm_agent_id_unique(self):
        from pptgenius.agent.common.model_builder import build_llm
        ids = {build_llm(1)[1] for _ in range(10)}
        assert len(ids) == 10

    def test_build_llm_middleware_has_correct_ids(self):
        from pptgenius.agent.common.model_builder import build_llm
        _, agent_id, mw = build_llm(42)
        assert mw.conversation_id == 42
        assert mw.agent_id == agent_id
