"""Tests for the coordinator agent — intent classification and dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from pptgenius.agent.coordinator import (
    CoordinatorDecision,
    _classify_intent,
    _load_coordinator_prompt,
    run_coordinator,
)


# ── prompt loading ───────────────────────────────────────────────────────────


def test_load_coordinator_prompt():
    prompt = _load_coordinator_prompt()
    assert len(prompt) > 200
    assert "generate_outline" in prompt
    assert "modify_outline" in prompt
    assert "generate_ppt" in prompt
    assert "modify_ppt" in prompt


# ── intent classification ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_generate_outline_no_outline():
    """Without any outline, a creation request should map to generate_outline."""
    mock_decision = CoordinatorDecision(
        task="generate_outline",
        reasoning="用户要求创建PPT，当前无大纲",
    )
    mock_model = MagicMock()
    mock_model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=mock_decision)

    with patch("pptgenius.agent.coordinator._get_model", return_value=mock_model):
        result = await _classify_intent(
            query="帮我做一个关于人工智能发展史的PPT",
            has_outline=False,
            has_ppt=False,
        )
    assert result.task == "generate_outline"


@pytest.mark.asyncio
async def test_classify_modify_outline():
    """With an outline, a modification request should map to modify_outline."""
    mock_decision = CoordinatorDecision(
        task="modify_outline",
        reasoning="用户要求增加案例，当前已有大纲",
    )
    mock_model = MagicMock()
    mock_model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=mock_decision)

    with patch("pptgenius.agent.coordinator._get_model", return_value=mock_model):
        result = await _classify_intent(
            query="加一个案例分析的部分",
            has_outline=True,
            has_ppt=False,
            outline_title="AI发展史",
        )
    assert result.task == "modify_outline"


@pytest.mark.asyncio
async def test_classify_generate_ppt():
    """A confirmation message with an outline should map to generate_ppt."""
    mock_decision = CoordinatorDecision(
        task="generate_ppt",
        reasoning="用户确认大纲，要求生成PPT",
    )
    mock_model = MagicMock()
    mock_model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=mock_decision)

    with patch("pptgenius.agent.coordinator._get_model", return_value=mock_model):
        result = await _classify_intent(
            query="没问题，开始生成PPT吧",
            has_outline=True,
            has_ppt=False,
            outline_title="AI发展史",
        )
    assert result.task == "generate_ppt"


@pytest.mark.asyncio
async def test_classify_modify_ppt():
    """A modification request with an existing PPT should map to modify_ppt."""
    mock_decision = CoordinatorDecision(
        task="modify_ppt",
        reasoning="用户要求修改PPT第3页的配色",
    )
    mock_model = MagicMock()
    mock_model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=mock_decision)

    with patch("pptgenius.agent.coordinator._get_model", return_value=mock_model):
        result = await _classify_intent(
            query="第3页的配色不好看，换个蓝色调的",
            has_outline=True,
            has_ppt=True,
            outline_title="AI发展史",
        )
    assert result.task == "modify_ppt"


# ── CoordinatorDecision model ─────────────────────────────────────────────────


def test_coordinator_decision_validation():
    """CoordinatorDecision should only accept valid task values."""
    d = CoordinatorDecision(task="generate_outline", reasoning="test")
    assert d.task == "generate_outline"

    d2 = CoordinatorDecision(task="modify_ppt", reasoning="test")
    assert d2.task == "modify_ppt"


def test_coordinator_decision_invalid():
    """Invalid task values should raise ValidationError."""
    with pytest.raises(Exception):
        CoordinatorDecision(task="invalid_task", reasoning="test")


# ── coordinator dispatch (integration) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_coordinator_generate_outline(db):
    """Coordinator should dispatch to outline agent for generate_outline task."""
    from pptgenius.infrastructure.db import Database
    from pptgenius.infrastructure.db.models import Conversation, User

    database = Database(db)

    user = User(name="test")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    conv = Conversation(user_id=user.id, title="测试")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    mock_decision = CoordinatorDecision(task="generate_outline", reasoning="新大纲")

    # Mock the LLM for intent classification
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=mock_decision)

    # Mock for the outline generator node (calls write_outline)
    gen_response = AIMessage(
        content="",
        tool_calls=[{
            "name": "write_outline",
            "args": {
                "title": "测试大纲",
                "design_rationale": "测试",
                "slides": [{
                    "slide_index": 0, "title": "首页",
                    "content_json": {"main_points": ["测试"]},
                    "layout_type": "title",
                    "has_image": False, "has_chart": False, "notes": "",
                }],
            },
            "id": "call_gen",
            "type": "tool_call",
        }],
    )
    # Mock for the evaluator node (calls submit_evaluation with high score → stops loop)
    eval_response = AIMessage(
        content="",
        tool_calls=[{
            "name": "submit_evaluation",
            "args": {
                "structure_clarity": 9.0,
                "logic_coherence": 9.0,
                "comprehensiveness": 9.0,
                "suggestions": "很好了",
            },
            "id": "call_eval",
            "type": "tool_call",
        }],
    )
    mock_gen_model = MagicMock(bind_tools=MagicMock(return_value=MagicMock(ainvoke=AsyncMock(return_value=gen_response))))
    mock_eval_model = MagicMock(bind_tools=MagicMock(return_value=MagicMock(ainvoke=AsyncMock(return_value=eval_response))))

    with patch("pptgenius.agent.coordinator._get_model", return_value=mock_llm), \
         patch("pptgenius.agent.outline.generator._get_model", return_value=mock_gen_model), \
         patch("pptgenius.agent.outline.evaluator._get_model", return_value=mock_eval_model):
        events = []
        async for event in run_coordinator(database, conv.id, "帮我做一个关于AI的PPT"):
            events.append(event)

    assert len(events) > 0
    # Should contain a phase event for the task
    phase_events = [e for e in events if "generate_outline" in e]
    assert len(phase_events) >= 1
    # Should contain an outline event with outline_id
    outline_events = [e for e in events if "outline_id" in e]
    assert len(outline_events) >= 1


@pytest.mark.asyncio
async def test_run_coordinator_modify_outline(db):
    """Coordinator should dispatch to outline agent for modify_outline task."""
    from pptgenius.infrastructure.db import Database
    from pptgenius.infrastructure.db.models import Conversation, User

    database = Database(db)

    user = User(name="test")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    conv = Conversation(user_id=user.id, title="测试")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    # Create an existing outline
    outline = await database.create_outline(
        user_id=user.id, conversation_id=conv.id, title="旧大纲", slide_count=1
    )
    await database.create_outline_slide(
        outline_id=outline.id, slide_index=0, title="旧页",
        content_json={"main_points": ["旧"]}
    )

    mock_decision = CoordinatorDecision(task="modify_outline", reasoning="修改大纲")

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=mock_decision)

    gen_response = AIMessage(
        content="",
        tool_calls=[{
            "name": "write_outline",
            "args": {
                "title": "修改后的大纲",
                "design_rationale": "改进",
                "slides": [{
                    "slide_index": 0, "title": "新页",
                    "content_json": {"main_points": ["新内容"]},
                    "layout_type": "content",
                    "has_image": False, "has_chart": False, "notes": "",
                }],
            },
            "id": "call_1",
            "type": "tool_call",
        }],
    )
    # Evaluator mock (high score → stops loop)
    eval_response = AIMessage(
        content="",
        tool_calls=[{
            "name": "submit_evaluation",
            "args": {
                "structure_clarity": 9.0, "logic_coherence": 9.0,
                "comprehensiveness": 9.0, "suggestions": "OK",
            },
            "id": "call_ev",
            "type": "tool_call",
        }],
    )
    mock_gen = MagicMock(bind_tools=MagicMock(return_value=MagicMock(ainvoke=AsyncMock(return_value=gen_response))))
    mock_eval = MagicMock(bind_tools=MagicMock(return_value=MagicMock(ainvoke=AsyncMock(return_value=eval_response))))

    with patch("pptgenius.agent.coordinator._get_model", return_value=mock_llm), \
         patch("pptgenius.agent.outline.generator._get_model", return_value=mock_gen), \
         patch("pptgenius.agent.outline.evaluator._get_model", return_value=mock_eval):
        events = []
        async for event in run_coordinator(database, conv.id, "加一个案例研究"):
            events.append(event)

    assert len(events) > 0
    # Should contain outline event with modified content
    outline_events = [e for e in events if "新页" in e]
    assert len(outline_events) >= 1


@pytest.mark.asyncio
async def test_run_coordinator_generate_ppt_no_outline(db):
    """Coordinator should error if generate_ppt requested but no outline exists."""
    from pptgenius.infrastructure.db import Database
    from pptgenius.infrastructure.db.models import Conversation, User

    database = Database(db)

    user = User(name="test")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    conv = Conversation(user_id=user.id, title="测试")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    mock_decision = CoordinatorDecision(task="generate_ppt", reasoning="生成PPT")

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=mock_decision)

    with patch("pptgenius.agent.coordinator._get_model", return_value=mock_llm):
        events = []
        async for event in run_coordinator(database, conv.id, "生成PPT"):
            events.append(event)

    # Should get an error since no outline exists
    error_events = [e for e in events if "error" in e]
    assert len(error_events) >= 1


@pytest.mark.asyncio
async def test_run_coordinator_conversation_not_found(db):
    """Coordinator should return error for non-existent conversation."""
    from pptgenius.infrastructure.db import Database

    database = Database(db)
    events = []
    async for event in run_coordinator(database, 99999, "hello"):
        events.append(event)

    assert len(events) == 1
    assert "error" in events[0]
    assert "40001" in events[0]
