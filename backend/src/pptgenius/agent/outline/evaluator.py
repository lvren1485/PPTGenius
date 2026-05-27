"""Evaluator node — scores an outline against the rubric and writes results.

The evaluator has one tool:
- ``submit_evaluation`` — persist scores + suggestions to DB (terminal tool)
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

from .prompts import (
    build_evaluator_user_prompt,
    format_rubric_for_prompt,
    load_evaluator_system,
)
from .state import OutlineState

_log = get_logger("pptgenius.agent.outline.evaluator")


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        temperature=0.3,  # lower temperature for evaluation
        max_tokens=cfg.max_tokens,
    )


def _format_slides_text(slides: list) -> str:
    """Format outline slides as readable text for the evaluator."""
    parts = []
    for s in slides:
        parts.append(f"### 第{s.slide_index + 1}页：{s.title}")
        parts.append(f"布局类型: {s.layout_type}")
        if s.content_json:
            cj = s.content_json
            if isinstance(cj, dict):
                for key in ("main_points", "detailed_content", "key_data", "visual_note"):
                    val = cj.get(key)
                    if val:
                        if isinstance(val, list):
                            parts.append(f"{key}: {'; '.join(val)}")
                        else:
                            parts.append(f"{key}: {val}")
            else:
                parts.append(str(cj))
        if s.notes:
            parts.append(f"备注: {s.notes}")
        if s.has_image:
            parts.append("[需要图片]")
        if s.has_chart:
            parts.append("[需要图表]")
        parts.append("")
    return "\n".join(parts)


def _make_submit_evaluation(db: Database, outline_id: int):
    @tool
    async def submit_evaluation(
        structure_clarity: float,
        logic_coherence: float,
        comprehensiveness: float,
        suggestions: str,
    ) -> str:
        """Submit evaluation scores for the current outline. MUST be called as the final action.

        Parameters
        ----------
        structure_clarity : float
            Score for structure clarity (0-10).
        logic_coherence : float
            Score for logic coherence (0-10).
        comprehensiveness : float
            Score for comprehensiveness (0-10).
        suggestions : str
            Specific, actionable improvement suggestions.
        """
        total = round((structure_clarity + logic_coherence + comprehensiveness) / 3, 2)
        await db.update_outline_eval(outline_id, total)
        _log.info("evaluation submitted for outline %d: %.2f", outline_id, total)
        return json.dumps({
            "structure_clarity": structure_clarity,
            "logic_coherence": logic_coherence,
            "comprehensiveness": comprehensiveness,
            "total": total,
            "suggestions": suggestions,
        })

    return submit_evaluation


# ── evaluator node ──────────────────────────────────────────────────────────


async def evaluator_node(state: OutlineState, config: RunnableConfig) -> dict:
    """Evaluator agent: read outline → score → submit_evaluation.

    Reads the current outline + slides from DB, asks the LLM to score against
    the rubric, and writes the results.
    """
    db: Database = config["configurable"]["db"]
    outline_id = state["outline_id"]

    if outline_id is None:
        _log.error("evaluator called with no outline_id")
        return {"evaluated": True, "eval_score": 0.0, "eval_suggestions": "无大纲可评估"}

    outline = await db.get_outline(outline_id)
    if outline is None:
        _log.error("outline %d not found", outline_id)
        return {"evaluated": True, "eval_score": 0.0, "eval_suggestions": "大纲未找到"}

    slides = await db.get_slides_by_outline_id(outline_id)
    slides_text = _format_slides_text(slides)

    model = _get_model()
    submit_tool = _make_submit_evaluation(db, outline_id)
    tools = [submit_tool]
    tools_by_name = {t.name: t for t in tools}
    model_with_tools = model.bind_tools(tools)

    rubric_text = format_rubric_for_prompt()
    system_prompt = load_evaluator_system() + "\n\n" + rubric_text
    user_prompt = build_evaluator_user_prompt(
        outline_title=outline.title,
        slides_text=slides_text,
        design_rationale=state.get("design_rationale", ""),
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    eval_score: float = 0.0
    eval_suggestions = ""

    for _turn in range(10):
        response = await model_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            _log.warning("evaluator stopped without calling submit_evaluation")
            break

        for tc in response.tool_calls:
            tool_func = tools_by_name.get(tc["name"])
            if tool_func is None:
                messages.append(ToolMessage(
                    content=f"Unknown tool: {tc['name']}", tool_call_id=tc["id"]
                ))
                continue

            try:
                result = await tool_func.ainvoke(tc["args"])
            except Exception as exc:
                _log.exception("submit_evaluation failed")
                result = f"Tool error: {exc}"

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

            if tc["name"] == "submit_evaluation":
                parsed = json.loads(str(result))
                eval_score = parsed["total"]
                eval_suggestions = parsed.get("suggestions", "")
                break

        if eval_score > 0 or any(tc["name"] == "submit_evaluation" for tc in response.tool_calls):
            break

    return {
        "evaluated": True,
        "eval_score": eval_score,
        "eval_suggestions": eval_suggestions,
        "query": eval_suggestions,  # becomes next round's generator input
        "messages": messages,
    }
