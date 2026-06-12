"""Outline evaluator sub-agent — ReAct agent for evaluating outline quality."""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.model_builder import build_llm
from .prompts import (
    build_evaluator_system_prompt,
    compute_outline_metrics,
    format_metrics_for_prompt,
)

_log = get_logger("pptgenius.agent.outline.evaluator")


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


# ── tool ──────────────────────────────────────────────────────────────────────


def _make_submit_evaluation(db: Database, outline_id: int):
    @tool
    async def submit_evaluation(
        structure_clarity: float,
        logic_coherence: float,
        comprehensiveness: float,
        visual_diversity: float,
        content_richness: float,
        suggestions: str,
    ) -> str:
        """Submit evaluation scores. MUST be called last.

        Parameters
        ----------
        structure_clarity : float — Score 0-10 for structure clarity.
        logic_coherence : float — Score 0-10 for logic coherence.
        comprehensiveness : float — Score 0-10 for comprehensiveness.
        visual_diversity : float — Score 0-10 for visual element diversity.
        content_richness : float — Score 0-10 for content richness (slide count + text length).
        suggestions : str — Specific, actionable improvement suggestions.
        """
        total = round(
            (structure_clarity + logic_coherence + comprehensiveness
             + visual_diversity + content_richness) / 5,
            2,
        )
        overall = (
            f"总分 {total}/10 | 结构{structure_clarity} 逻辑{logic_coherence} "
            f"全面{comprehensiveness} 视觉{visual_diversity} 内容{content_richness}"
        )
        await db.update_outline_eval(outline_id, total)
        _log.info("evaluation submitted for outline %d: %.2f", outline_id, total)
        return json.dumps({
            "structure_clarity": structure_clarity,
            "logic_coherence": logic_coherence,
            "comprehensiveness": comprehensiveness,
            "visual_diversity": visual_diversity,
            "content_richness": content_richness,
            "total": total,
            "suggestions": suggestions,
        })

    return submit_evaluation


# ── helpers ───────────────────────────────────────────────────────────────────


def _format_slides_text(slides: list) -> str:
    parts = []
    for s in slides:
        parts.append(f"### 第{s.slide_index}页：{s.title}")
        parts.append(f"布局类型: {s.layout_type}")
        if s.content_json:
            cj = s.content_json
            if isinstance(cj, dict):
                for key in ("main_points", "detailed_content", "key_data",
                            "visual_note", "recommended_ppt_format"):
                    val = cj.get(key)
                    if val:
                        parts.append(f"{key}: {'; '.join(val) if isinstance(val, list) else val}")
        if s.notes:
            parts.append(f"备注: {s.notes}")
        if s.has_image:
            parts.append("[需要图片]")
        if s.has_chart:
            parts.append("[需要图表]")
        parts.append("")
    return "\n".join(parts)


# ── main entry ────────────────────────────────────────────────────────────────


async def run_outline_evaluator(
    db: Database,
    conversation_id: int,
    query: str | None = None,
) -> dict:
    """Evaluate the current outline and return scores + suggestions.

    Returns ``{overall: str, suggestions: list[str], score: float}``.
    """
    writer = _get_writer()

    conv = await db.get_conversation(conversation_id)
    if conv is None or conv.current_outline_id is None:
        return {"error": "没有选中大纲"}

    outline_id = conv.current_outline_id
    outline = await db.get_outline(outline_id)
    if outline is None:
        return {"error": "大纲不存在"}

    slides = await db.get_slides_by_outline_id(outline_id)
    slides_text = _format_slides_text(slides)
    metrics = compute_outline_metrics(slides)

    system_prompt = build_evaluator_system_prompt()

    user_prompt_parts = [
        "请对以下PPT大纲进行评审打分。",
        "",
        f"## 大纲标题：{outline.title}",
    ]
    if query:
        user_prompt_parts.extend(["", "## 用户原始需求", "", query])
    if metrics:
        user_prompt_parts.extend([
            "",
            "## 大纲量化指标（程序自动计算，供参考）",
            "",
            format_metrics_for_prompt(metrics),
        ])
    user_prompt_parts.extend([
        "",
        "---",
        "请严格对照评分标准对五个维度分别打分（含 content_richness）。",
        "如果量化指标显示明显问题（如 content 页平均 detailed_content 低于300字），必须在对应维度扣分。",
        "content_richness 仅看文本长度，不因页数扣分。",
        "**必须使用 submit_evaluation 工具提交评分。**",
        "",
        "## 大纲内容",
        "",
        slides_text,
    ])
    user_prompt = "\n".join(user_prompt_parts)

    llm, agent_id, mw = build_llm(conversation_id)
    push_agent(conversation_id, agent_id)
    agent = create_agent(
        model=llm,
        tools=[_make_submit_evaluation(db, outline_id)],
        system_prompt=system_prompt,
        middleware=[mw],
    )

    writer({"type": "outline_evaluator_start", "outline": outline.title})
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config={"recursion_limit": 20},
    )
    writer({"type": "outline_evaluator_end"})

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

    return {
        "overall": f"总分 {eval_score}/10",
        "score": eval_score,
        "suggestions": eval_suggestions,
    }
