"""Evaluator agent — uses LangChain create_agent for the ReAct loop.

The evaluator has one tool:
- ``submit_evaluation`` — persist scores + suggestions to DB (terminal tool)
"""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

from .middleware import TokenCountingMiddleware
from .prompts import (
    build_evaluator_user_prompt,
    compute_outline_metrics,
    format_rubric_for_prompt,
    load_evaluator_system,
)
from .state import OutlineState

_log = get_logger("pptgenius.agent.outline.evaluator")

apply_deepseek_patch()


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        temperature=0.3,
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
                for key in ("main_points", "detailed_content", "key_data",
                            "visual_note", "recommended_ppt_format"):
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
        visual_diversity: float,
        suggestions: str,
    ) -> str:
        """Submit evaluation scores for the current outline. MUST be called last.

        Parameters
        ----------
        structure_clarity : float — Score for structure clarity (0-10).
        logic_coherence : float — Score for logic coherence (0-10).
        comprehensiveness : float — Score for comprehensiveness (0-10).
        visual_diversity : float — Score for visual element diversity (0-10).
        suggestions : str — Specific, actionable improvement suggestions.
        """
        total = round((structure_clarity + logic_coherence + comprehensiveness + visual_diversity) / 4, 2)
        await db.update_outline_eval(outline_id, total)
        _log.info("evaluation submitted for outline %d: %.2f", outline_id, total)
        return json.dumps({
            "structure_clarity": structure_clarity,
            "logic_coherence": logic_coherence,
            "comprehensiveness": comprehensiveness,
            "visual_diversity": visual_diversity,
            "total": total,
            "suggestions": suggestions,
        })

    return submit_evaluation


# ── evaluator node ───────────────────────────────────────────────────────────


async def evaluator_node(state: OutlineState, config: RunnableConfig) -> dict:
    """Evaluator: read outline → build prompt → create_agent → extract scores."""
    db: Database = config["configurable"]["db"]
    outline_id = state["outline_id"]
    conv_id = state["conversation_id"]

    if outline_id is None:
        _log.error("evaluator called with no outline_id")
        return {"evaluated": True, "eval_score": 0.0, "eval_suggestions": "无大纲可评估"}

    outline = await db.get_outline(outline_id)
    if outline is None:
        _log.error("outline %d not found", outline_id)
        return {"evaluated": True, "eval_score": 0.0, "eval_suggestions": "大纲未找到"}

    slides = await db.get_slides_by_outline_id(outline_id)
    slides_text = _format_slides_text(slides)
    metrics = compute_outline_metrics(slides)

    rubric_text = format_rubric_for_prompt()
    system_prompt = load_evaluator_system() + "\n\n" + rubric_text

    design_rationales = state.get("design_rationales", [])
    user_prompt = build_evaluator_user_prompt(
        outline_title=outline.title,
        slides_text=slides_text,
        design_rationale="\n---\n".join(design_rationales) if design_rationales else "",
        metrics=metrics,
    )

    agent = create_agent(
        model=_get_model(),
        tools=[_make_submit_evaluation(db, outline_id)],
        system_prompt=system_prompt,
        middleware=[TokenCountingMiddleware(conv_id)],
    )

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config=config,
    )

    # Extract scores from submit_evaluation ToolMessage
    eval_score: float = 0.0
    eval_suggestions = ""
    for msg in reversed(result["messages"]):
        name = getattr(msg, "name", None)
        if name == "submit_evaluation":
            try:
                parsed = json.loads(str(msg.content))
                eval_score = parsed.get("total", 0.0)
                eval_suggestions = parsed.get("suggestions", "")
            except (json.JSONDecodeError, TypeError):
                pass
            break
    else:
        # Fallback: try to parse any ToolMessage content that looks like eval result
        for msg in reversed(result["messages"]):
            if hasattr(msg, "tool_call_id"):
                try:
                    parsed = json.loads(str(msg.content))
                    if "total" in parsed and "structure_clarity" in parsed:
                        eval_score = parsed.get("total", 0.0)
                        eval_suggestions = parsed.get("suggestions", "")
                        break
                except (json.JSONDecodeError, TypeError):
                    pass

    return {
        "evaluated": True,
        "eval_score": eval_score,
        "eval_suggestions": eval_suggestions,
        "query": eval_suggestions,
        "messages": result["messages"],
    }
