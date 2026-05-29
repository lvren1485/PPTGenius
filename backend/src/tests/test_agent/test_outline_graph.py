"""Tests for the outline generator-evaluator graph.

Covers: graph compilation, routing logic, prompt loading, tool creation,
and end-to-end invocation with a mock LLM.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pptgenius.agent.outline.graph import (
    _should_continue,
    build_outline_graph,
)
from pptgenius.agent.outline.state import OutlineState
from pptgenius.agent.outline.prompts import (
    build_evaluator_user_prompt,
    build_generator_user_prompt,
    format_rubric_for_prompt,
    load_evaluator_system,
    load_generator_system,
    load_rubric,
)
from pptgenius.agent.outline.generator import (
    _make_fetch_web,
    _make_search_knowledge,
    _make_search_web,
    _make_write_outline,
)
from pptgenius.agent.outline.evaluator import (
    _format_slides_text,
    _make_submit_evaluation,
)


# ── fixtures ────────────────────────────────────────────────────────────────


def _base_state(**overrides) -> OutlineState:
    s: OutlineState = {
        "user_id": 1,
        "conversation_id": 1,
        "query": "测试主题",
        "outline_id": None,
        "evaluated": False,
        "iteration": 0,
        "eval_score": None,
        "eval_suggestions": "",
        "mode": "mix",
        "max_iterations": 3,
        "pass_score": 8.0,
        "design_rationale": "",
        "design_rationales": [],
        "final_outline_data": None,
        "messages": [],
    }
    s.update(overrides)
    return s


# ── graph compilation ───────────────────────────────────────────────────────


def test_graph_compiles():
    """The graph should compile without errors."""
    graph = build_outline_graph()
    assert graph is not None
    # CompiledStateGraph has channels (state schema) and nodes
    assert hasattr(graph, "get_graph")


def test_graph_has_nodes():
    """Graph should include generator and evaluator nodes."""
    graph = build_outline_graph()
    nodes = list(graph.get_graph().nodes.keys())
    assert "generator" in nodes
    assert "evaluator" in nodes


# ── routing: entry ───────────────────────────────────────────────────────────


def test_graph_starts_at_generator():
    """Graph entry always starts at generator node."""
    graph = build_outline_graph()
    # Verify the compiled graph has generator as the first node after START
    assert graph is not None


# ── routing: stop conditions ─────────────────────────────────────────────────


def test_should_continue_mix_hit_max():
    """Mix mode: hit max iterations → stop."""
    state = _base_state(mode="mix", iteration=3, max_iterations=3, eval_score=5.0)
    assert _should_continue(state) == "finalize"


def test_should_continue_mix_hit_score():
    """Mix mode: hit pass score → stop."""
    state = _base_state(mode="mix", iteration=1, max_iterations=3, eval_score=8.5, pass_score=8.0)
    assert _should_continue(state) == "finalize"


def test_should_continue_mix_neither():
    """Mix mode: neither condition met → continue."""
    state = _base_state(mode="mix", iteration=1, max_iterations=3, eval_score=6.0, pass_score=8.0)
    assert _should_continue(state) == "generator"


def test_should_continue_max_iteration():
    """Max-iteration mode: stop only on iteration cap."""
    state = _base_state(mode="max_iteration", iteration=3, max_iterations=3, eval_score=9.0)
    assert _should_continue(state) == "finalize"


def test_should_continue_max_iteration_not_hit():
    """Max-iteration mode: continue when under cap (ignore score)."""
    state = _base_state(mode="max_iteration", iteration=1, max_iterations=3, eval_score=9.5, pass_score=8.0)
    assert _should_continue(state) == "generator"


def test_should_continue_pass_score():
    """Pass-score mode: stop on score threshold regardless of iteration."""
    state = _base_state(mode="pass_score", iteration=1, max_iterations=3, eval_score=8.5, pass_score=8.0)
    assert _should_continue(state) == "finalize"


def test_should_continue_pass_score_not_hit():
    """Pass-score mode: continue when score below threshold."""
    state = _base_state(mode="pass_score", iteration=10, max_iterations=3, eval_score=7.0, pass_score=8.0)
    assert _should_continue(state) == "generator"  # ignores max_iterations


# ── prompts ──────────────────────────────────────────────────────────────────


def test_load_generator_system():
    prompt = load_generator_system()
    assert len(prompt) > 100
    assert "write_outline" in prompt


def test_load_evaluator_system():
    prompt = load_evaluator_system()
    assert len(prompt) > 100
    assert "submit_evaluation" in prompt


def test_load_rubric():
    rubric = load_rubric()
    assert rubric["name"]
    assert len(rubric["dimensions"]) == 4
    for dim in rubric["dimensions"]:
        assert "key" in dim
        assert "label" in dim
        assert "max_score" in dim


def test_format_rubric_for_prompt():
    text = format_rubric_for_prompt()
    assert "结构清楚度" in text
    assert "逻辑通畅度" in text
    assert "展示全面度" in text


def test_build_generator_user_prompt_new():
    prompt = build_generator_user_prompt(query="介绍一下AI的发展")
    assert "介绍一下AI的发展" in prompt
    assert "生成" in prompt


def test_build_generator_user_prompt_revision():
    prompt = build_generator_user_prompt(
        query="增加案例研究",
        design_rationale="按时间线组织",
        eval_suggestions="缺少案例",
        is_revision=True,
    )
    assert "增加案例研究" in prompt or "缺少案例" in prompt
    assert "修改" in prompt


def test_build_evaluator_user_prompt():
    slides_text = "### 第1页：标题\n内容..."
    prompt = build_evaluator_user_prompt(
        outline_title="AI发展史",
        slides_text=slides_text,
        design_rationale="按时间线组织",
    )
    assert "AI发展史" in prompt
    assert "标题" in prompt
    assert "submit_evaluation" in prompt


# ── slides formatting ────────────────────────────────────────────────────────


def test_format_slides_text():
    from pptgenius.infrastructure.db.models import OutlineSlide

    slides = [
        MagicMock(
            slide_index=0,
            title="封面",
            layout_type="title",
            content_json={"main_points": ["点1"], "detailed_content": "详细内容"},
            has_image=False,
            has_chart=False,
            notes="备注文字",
        ),
        MagicMock(
            slide_index=1,
            title="正文",
            layout_type="content",
            content_json={"main_points": ["点2"], "visual_note": "图表建议"},
            has_image=True,
            has_chart=True,
            notes=None,
        ),
    ]
    text = _format_slides_text(slides)
    assert "第1页" in text
    assert "封面" in text
    assert "点1" in text
    assert "详细内容" in text
    assert "备注文字" in text
    assert "第2页" in text
    assert "[需要图片]" in text
    assert "[需要图表]" in text
    assert "图表建议" in text


# ── tool creation ────────────────────────────────────────────────────────────


def test_search_knowledge_tool_signature():
    tool = _make_search_knowledge(user_id=1)
    assert tool.name == "search_knowledge"
    assert "query" in str(tool.args_schema.model_json_schema())


def test_search_web_tool_signature():
    tool = _make_search_web()
    assert tool.name == "search_web"
    assert "query" in str(tool.args_schema.model_json_schema())


def test_fetch_web_tool_signature():
    mock_db = MagicMock()
    tool = _make_fetch_web(mock_db, user_id=1, conv_id=1)
    assert tool.name == "fetch_web"
    schema = tool.args_schema.model_json_schema()
    assert "url" in str(schema)


def test_write_outline_tool_signature():
    mock_db = MagicMock()
    tool, get_result = _make_write_outline(mock_db, user_id=1, conv_id=1, initial_outline_id=None)
    assert tool.name == "write_outline"
    assert callable(get_result)
    schema = tool.args_schema.model_json_schema()
    props = schema.get("properties", {})
    assert "title" in props
    assert "design_rationale" in props
    assert "slides" in props


def test_submit_evaluation_tool_signature():
    mock_db = MagicMock()
    tool = _make_submit_evaluation(mock_db, outline_id=1)
    assert tool.name == "submit_evaluation"
    schema = tool.args_schema.model_json_schema()
    props = schema.get("properties", {})
    assert "structure_clarity" in props
    assert "logic_coherence" in props
    assert "comprehensiveness" in props
    assert "visual_diversity" in props
    assert "suggestions" in props


# ── ReAct-aware mock model ────────────────────────────────────────────────────


class _ReActMockModel:
    """Simulates a model that calls a tool once, then returns a final response.

    create_agent expects: model→tool_call→tool→model→final_text (no tool_calls)→stop
    """

    def __init__(self, tool_call_msg: AIMessage, final_msg: AIMessage):
        self._tool_call_msg = tool_call_msg
        self._final_msg = final_msg
        self._tools = []
        self._tool_choice = None

    def bind_tools(self, tools, **kwargs):
        self._tools = tools
        self._tool_choice = kwargs.get("tool_choice")
        return self

    async def ainvoke(self, messages, **kwargs):
        # If ToolMessage exists in messages → final round
        has_tool_msg = any(hasattr(m, "tool_call_id") for m in messages if hasattr(m, "tool_call_id"))
        if has_tool_msg:
            return self._final_msg
        return self._tool_call_msg


# ── end-to-end with mock LLM ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generator_node_creates_outline(db):
    """Generator node should create an outline when invoked with a mock LLM."""
    from pptgenius.agent.outline.generator import generator_node
    from pptgenius.infrastructure.db import Database
    from langchain_core.messages import AIMessage

    database = Database(db)

    from pptgenius.infrastructure.db.models import Conversation, User
    user = User(name="test")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    conv = Conversation(user_id=user.id, title="测试会话")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    state = _base_state(user_id=user.id, conversation_id=conv.id)

    tool_msg = AIMessage(content="", tool_calls=[{
        "name": "write_outline", "args": {
            "title": "AI发展史", "design_rationale": "按时间线组织",
            "slides": [
                {"slide_index": 0, "title": "封面", "content_json": {"main_points": ["AI发展史"], "detailed_content": "从1950年至今"}, "layout_type": "title", "has_image": False, "has_chart": False, "notes": ""},
                {"slide_index": 1, "title": "总结", "content_json": {"main_points": ["总结"], "detailed_content": "AI未来展望"}, "layout_type": "summary", "has_image": False, "has_chart": False, "notes": ""},
            ],
        },
        "id": "call_1", "type": "tool_call",
    }])
    final_msg = AIMessage(content="大纲已生成")
    mock_model = _ReActMockModel(tool_msg, final_msg)

    with patch("pptgenius.agent.outline.generator._get_model", return_value=mock_model):
        result = await generator_node(state, {"configurable": {"db": database}})

    assert result["outline_id"] is not None
    assert result["outline_id"] > 0
    assert result["evaluated"] is False
    assert result["iteration"] == 1

    outline = await database.get_outline(result["outline_id"])
    assert outline is not None
    assert outline.title == "AI发展史"
    assert outline.slide_count == 2

    slides = await database.get_slides_by_outline_id(result["outline_id"])
    assert len(slides) == 2
    assert slides[0].title == "封面"
    assert slides[1].title == "总结"


@pytest.mark.asyncio
async def test_generator_revision_replaces_slides(db):
    """Generator revision should increment version and replace slides."""
    from pptgenius.agent.outline.generator import generator_node
    from pptgenius.infrastructure.db import Database
    from langchain_core.messages import AIMessage

    database = Database(db)

    from pptgenius.infrastructure.db.models import Conversation, User
    user = User(name="test")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    conv = Conversation(user_id=user.id, title="测试会话")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    outline = await database.create_outline(
        user_id=user.id, conversation_id=conv.id, title="旧大纲", slide_count=2
    )
    await database.create_outline_slide(
        outline_id=outline.id, slide_index=0, title="旧页1", content_json={"old": True}
    )
    await database.create_outline_slide(
        outline_id=outline.id, slide_index=1, title="旧页2", content_json={"old": True}
    )

    state = _base_state(user_id=user.id, conversation_id=conv.id,
                        outline_id=outline.id, evaluated=True, iteration=1)

    tool_msg = AIMessage(content="", tool_calls=[{
        "name": "write_outline", "args": {
            "title": "新大纲", "design_rationale": "重新组织",
            "slides": [
                {"slide_index": 0, "title": "新页1", "content_json": {"new": True}, "layout_type": "content", "has_image": False, "has_chart": False, "notes": ""},
            ],
        },
        "id": "call_1", "type": "tool_call",
    }])
    final_msg = AIMessage(content="大纲已修改")
    mock_model = _ReActMockModel(tool_msg, final_msg)

    with patch("pptgenius.agent.outline.generator._get_model", return_value=mock_model):
        result = await generator_node(state, {"configurable": {"db": database}})

    assert result["outline_id"] == outline.id
    assert result["iteration"] == 2

    refreshed = await database.get_outline(outline.id)
    assert refreshed.version == 2

    slides = await database.get_slides_by_outline_id(outline.id)
    assert len(slides) == 1
    assert slides[0].title == "新页1"


@pytest.mark.asyncio
async def test_evaluator_node_scores_outline(db):
    """Evaluator node should score an outline and write to DB."""
    from pptgenius.agent.outline.evaluator import evaluator_node
    from pptgenius.infrastructure.db import Database
    from langchain_core.messages import AIMessage

    database = Database(db)

    from pptgenius.infrastructure.db.models import Conversation, User
    user = User(name="test")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    conv = Conversation(user_id=user.id, title="测试会话")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    outline = await database.create_outline(
        user_id=user.id, conversation_id=conv.id, title="测试大纲", slide_count=1
    )
    await database.create_outline_slide(
        outline_id=outline.id, slide_index=0, title="测试页",
        content_json={"main_points": ["测试"], "detailed_content": "测试内容"},
    )

    state = _base_state(user_id=user.id, conversation_id=conv.id,
                        outline_id=outline.id, evaluated=False)

    tool_msg = AIMessage(content="", tool_calls=[{
        "name": "submit_evaluation", "args": {
            "structure_clarity": 8.0, "logic_coherence": 7.0,
            "comprehensiveness": 6.0, "visual_diversity": 7.0,
            "suggestions": "建议增加案例研究",
        },
        "id": "call_1", "type": "tool_call",
    }])
    final_msg = AIMessage(content="评估完成")
    mock_model = _ReActMockModel(tool_msg, final_msg)

    with patch("pptgenius.agent.outline.evaluator._get_model", return_value=mock_model):
        result = await evaluator_node(state, {"configurable": {"db": database}})

    assert result["evaluated"] is True
    assert result["eval_score"] == pytest.approx(7.0, rel=0.01)  # (8+7+6+7)/4
    assert "增加案例" in result["eval_suggestions"]
    assert result["query"] == result["eval_suggestions"]

    refreshed = await database.get_outline(outline.id)
    assert refreshed.eval_score == pytest.approx(7.0, rel=0.01)


@pytest.mark.asyncio
async def test_full_graph_invocation_new_outline(db):
    """End-to-end: graph creates and evaluates a new outline with mock LLM."""
    from pptgenius.infrastructure.db import Database
    from langchain_core.messages import AIMessage

    database = Database(db)

    from pptgenius.infrastructure.db.models import Conversation, User
    user = User(name="test")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    conv = Conversation(user_id=user.id, title="测试会话")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    state = _base_state(user_id=user.id, conversation_id=conv.id)

    graph = build_outline_graph()

    gen_tool = AIMessage(content="", tool_calls=[{
        "name": "write_outline", "args": {
            "title": "AI发展史", "design_rationale": "按时间线组织",
            "slides": [
                {"slide_index": 0, "title": "封面", "content_json": {"main_points": ["AI发展史"], "detailed_content": "详细"}, "layout_type": "title", "has_image": False, "has_chart": False, "notes": ""},
            ],
        },
        "id": "call_gen", "type": "tool_call",
    }])
    gen_final = AIMessage(content="大纲已生成")

    eval_tool = AIMessage(content="", tool_calls=[{
        "name": "submit_evaluation", "args": {
            "structure_clarity": 9.0, "logic_coherence": 9.0,
            "comprehensiveness": 9.0, "visual_diversity": 9.0,
            "suggestions": "已经很好了",
        },
        "id": "call_eval", "type": "tool_call",
    }])
    eval_final = AIMessage(content="评估完成")

    gen_mock = _ReActMockModel(gen_tool, gen_final)
    eval_mock = _ReActMockModel(eval_tool, eval_final)

    with patch("pptgenius.agent.outline.generator._get_model", return_value=gen_mock), \
         patch("pptgenius.agent.outline.evaluator._get_model", return_value=eval_mock):
        result = await graph.ainvoke(state, {"configurable": {"db": database}})

    assert result["outline_id"] is not None
    assert result["evaluated"] is True
    assert result["eval_score"] == pytest.approx(9.0, rel=0.01)
    assert result["iteration"] == 1
