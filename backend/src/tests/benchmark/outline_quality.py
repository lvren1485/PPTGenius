"""B2: Outline quality — LLM-as-judge with quantified rubric (DeepSeek V4 Pro)."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pptgenius.infrastructure.config.settings import get_settings
from pptgenius.infrastructure.db.models import Conversation, Outline, OutlineSection, OutlineSlide

_JUDGE_PROMPT = """你是一个 PPT 大纲质量评审专家。请严格按照以下评分卡对大纲进行评分。

## 评分规则
- 每个维度独立打分 (1-10)，必须严格按照评分标准给分
- 每个维度给出 1 条扣分/优点理由
- 倾向于严格打分：没有明确证据支持高分时，给中间分
- 输出纯 JSON，不要加 ```json 标记

## 评分标准

### structure (结构合理性)
9-10: section 划分清晰均衡，每 section 3-6 页，覆盖主题全部核心方面
7-8: 划分合理但略有不均（某 section 页数过多/过少），覆盖面充分
5-6: 划分存在问题（过粗/过细/遗漏重要方面），但整体可用
3-4: 划分混乱，多个方面遗漏或重复
1-2: 无有效 section 结构

### coherence (页间逻辑连贯性)
9-10: 页面顺序形成清晰的叙事递进（总→分、因→果、问题→方案），过渡自然
7-8: 整体有逻辑线索但 1-2 处过渡生硬
5-6: 部分页面可独立但缺乏叙事线索
3-4: 页面顺序基本随意
1-2: 完全无逻辑组织

### richness (内容充实度)
9-10: 每页有 3+ 个具体要点，含数据/案例/引用，详细内容充实
7-8: 多数页有具体内容，少数页偏概括
5-6: 约半数页仅有概括性描述
3-4: 多数页仅一两句话
1-2: 几乎无实质内容

### visual (视觉建议合理性)
9-10: 每页都有合理的 recommended_ppt_format 和 visual_note，图表/图片建议贴合内容
7-8: 多数页有视觉建议且合理
5-6: 视觉建议存在但部分不合理
3-4: 大量缺失或明显不合理
1-2: 无视觉建议

## 大纲内容
{outline_json}

## 主题
{topic}

请输出 JSON（不要加代码块标记）:
{{"structure": {{"score": N, "reason": "..."}}, "coherence": {{"score": N, "reason": "..."}}, "richness": {{"score": N, "reason": "..."}}, "visual": {{"score": N, "reason": "..."}}}}"""

_DIMS = ("structure", "coherence", "richness", "visual")
_SAMPLES = 3


@dataclass
class OutlineScore:
    outline_id: int
    conv_title: str
    topic: str
    samples: list[dict] = field(default_factory=list)
    final_scores: dict[str, float] = field(default_factory=dict)
    avg_score: float = 0.0
    judge_cost: float = 0.0

    def compute_final(self):
        for dim in _DIMS:
            vals = [s[dim]["score"] for s in self.samples if dim in s]
            self.final_scores[dim] = statistics.median(vals) if vals else 0
        scores = list(self.final_scores.values())
        self.avg_score = sum(scores) / len(scores) if scores else 0


async def compute_outline_quality(
    session: AsyncSession, *, judge_model: str = "deepseek-chat",
) -> list[OutlineScore]:
    """Score all outlines using an LLM judge with quantified rubric."""
    settings = get_settings()
    llm = ChatOpenAI(
        model=judge_model,
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        temperature=0.3,
        max_tokens=1024,
    )

    conv_result = await session.execute(
        select(Conversation).where(Conversation.status != "deleted")
    )
    convs = {c.id: c for c in conv_result.scalars().all()}

    outline_result = await session.execute(
        select(Outline).where(Outline.status != "deleted")
    )
    outlines = list(outline_result.scalars().all())
    results: list[OutlineScore] = []

    for outline in outlines:
        conv = convs.get(outline.conversation_id)
        if not conv:
            continue

        outline_json = await _build_outline_text(session, outline)
        if not outline_json:
            continue

        score = OutlineScore(
            outline_id=outline.id,
            conv_title=conv.title or "",
            topic=outline.title or conv.title or "",
        )

        for _ in range(_SAMPLES):
            prompt = _JUDGE_PROMPT.format(
                outline_json=outline_json[:30_000],
                topic=score.topic,
            )
            try:
                resp = await llm.ainvoke(prompt)
                text = resp.content.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                parsed = json.loads(text)
                for dim in _DIMS:
                    if dim in parsed:
                        parsed[dim]["score"] = max(1, min(10, int(parsed[dim]["score"])))
                score.samples.append(parsed)
                usage = resp.response_metadata.get("token_usage", {})
                tokens = (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
                score.judge_cost += tokens * 2 / 1_000_000  # rough V4 Pro pricing
            except Exception:
                pass

        score.compute_final()
        results.append(score)

    return results


async def _build_outline_text(session: AsyncSession, outline: Outline) -> str:
    """Build a readable outline summary for the judge."""
    sec_result = await session.execute(
        select(OutlineSection).where(OutlineSection.outline_id == outline.id)
        .order_by(OutlineSection.section_index)
    )
    sections = list(sec_result.scalars().all())

    slide_result = await session.execute(
        select(OutlineSlide).where(OutlineSlide.outline_id == outline.id)
        .where(OutlineSlide.status != "deleted")
        .order_by(OutlineSlide.slide_index)
    )
    slides = list(slide_result.scalars().all())

    if not slides:
        return ""

    lines = [f"# {outline.title}", f"共 {len(slides)} 页, {len(sections)} 个章节", ""]
    for sec in sections:
        lines.append(f"## Section {sec.section_index}: {sec.title}")
        if sec.description:
            lines.append(f"  描述: {sec.description}")
        sec_slides = sorted(
            [s for s in slides if s.section_id == sec.id],
            key=lambda x: x.slide_index,
        )
        for sl in sec_slides:
            cj = sl.content_json or {}
            points = cj.get("main_points", [])
            detail = cj.get("detailed_content", "")
            fmt = cj.get("recommended_ppt_format", "")
            vnote = cj.get("visual_note", "")
            lines.append(f"  [{sl.slide_index}] {sl.title} ({sl.layout_type})")
            if points:
                for p in points[:5]:
                    lines.append(f"    - {p}")
            if detail:
                lines.append(f"    详细: {detail[:200]}")
            if fmt:
                lines.append(f"    格式建议: {fmt}")
            if vnote:
                lines.append(f"    视觉建议: {vnote[:100]}")
        lines.append("")

    return "\n".join(lines)
