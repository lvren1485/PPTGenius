"""B3: PPT visual quality — automated checks on agent_outputs JSON."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pptgenius.infrastructure.db.models import (
    Conversation, Presentation, PresentationSlide, Style,
)

SLIDE_W, SLIDE_H = 13.333, 7.5
MIN_FONT_SIZE = 11
Z_ORDER_REF = {"background": 0, "shape": 20, "picture": 30, "chart": 40,
               "table": 50, "textbox": 70, "title": 80}


@dataclass
class SlideVisualScore:
    slide_index: int
    element_count: int = 0
    out_of_bounds: int = 0
    overlaps: int = 0
    text_overflow: int = 0
    color_mismatches: int = 0
    small_font: int = 0
    z_order_violations: int = 0
    has_background: bool = False
    emoji_icon_conflict: bool = False
    parts_total: int = 0
    parts_complete: int = 0


@dataclass
class VisualQualityResult:
    pres_id: int
    conv_title: str
    slide_scores: list[SlideVisualScore] = field(default_factory=list)

    @property
    def total_elements(self) -> int:
        return sum(s.element_count for s in self.slide_scores)

    @property
    def out_of_bounds_rate(self) -> float:
        t = self.total_elements
        return sum(s.out_of_bounds for s in self.slide_scores) / t if t else 0

    @property
    def overlap_rate(self) -> float:
        t = self.total_elements
        return sum(s.overlaps for s in self.slide_scores) / t if t else 0

    @property
    def text_overflow_rate(self) -> float:
        tb = sum(1 for s in self.slide_scores for _ in range(s.element_count))
        return sum(s.text_overflow for s in self.slide_scores) / tb if tb else 0

    @property
    def background_rate(self) -> float:
        n = len(self.slide_scores)
        return sum(1 for s in self.slide_scores if s.has_background) / n if n else 0

    @property
    def part_completion_rate(self) -> float | None:
        """Only meaningful for Part-Based slides (those with a plan)."""
        total = sum(s.parts_total for s in self.slide_scores)
        done = sum(s.parts_complete for s in self.slide_scores)
        if total == 0:
            return None  # no plan data — pre-Part-Based PPT
        return done / total

    @property
    def decor_conflicts(self) -> int:
        return sum(1 for s in self.slide_scores if s.emoji_icon_conflict)


async def compute_visual_quality(session: AsyncSession) -> list[VisualQualityResult]:
    """Evaluate visual quality for all presentations."""
    conv_result = await session.execute(
        select(Conversation).where(Conversation.status != "deleted")
    )
    convs = {c.id: c for c in conv_result.scalars().all()}

    pres_result = await session.execute(
        select(Presentation).where(Presentation.status != "deleted")
    )
    presentations = list(pres_result.scalars().all())
    results: list[VisualQualityResult] = []

    for pres in presentations:
        conv = convs.get(pres.conversation_id)
        if not conv:
            continue

        slide_result = await session.execute(
            select(PresentationSlide)
            .where(PresentationSlide.presentation_id == pres.id)
            .where(PresentationSlide.status != "deleted")
            .order_by(PresentationSlide.slide_index)
        )
        slides = list(slide_result.scalars().all())

        style_colors = set()
        if pres.style_id:
            style = await session.get(Style, pres.style_id)
            if style and style.colors_json:
                style_colors = set(_extract_colors(style.colors_json))

        vr = VisualQualityResult(pres_id=pres.id, conv_title=conv.title or "")
        for sl in slides:
            ao = sl.agent_outputs or {}
            score = _check_slide(ao, sl.slide_index, style_colors)
            vr.slide_scores.append(score)
        results.append(vr)

    return results


def _check_slide(ao: dict, slide_index: int, style_colors: set[str]) -> SlideVisualScore:
    """Run all visual checks on one slide's agent_outputs."""
    elements = ao.get("elements", [])
    bg = ao.get("background", {})
    plan = ao.get("plan", {})

    score = SlideVisualScore(
        slide_index=slide_index,
        element_count=len(elements),
        has_background=bool(bg and bg.get("type")),
    )

    if plan and plan.get("parts"):
        parts = plan["parts"]
        score.parts_total = len(parts)
        score.parts_complete = sum(1 for p in parts.values() if p.get("status") == "complete")

    has_emoji = False
    has_icon = False

    for el in elements:
        pos = el.get("position") or {}
        left = pos.get("left") or 0
        top = pos.get("top") or 0
        width = pos.get("width") or 0
        height = pos.get("height") or 0

        if left + width > SLIDE_W + 0.5 or top + height > SLIDE_H + 0.5 or left < -0.5 or top < -0.5:
            score.out_of_bounds += 1

        el_type = el.get("type", "")
        if el_type == "textbox":
            fs = el.get("font_size") or (el.get("text_style") or {}).get("font_size") or 14
            if isinstance(fs, (int, float)) and fs < MIN_FONT_SIZE:
                score.small_font += 1
            text = el.get("text_content", "")
            if isinstance(text, str) and len(text) > 0:
                capacity = max(1, int(width * height * 15))
                if len(text) > capacity * 2:
                    score.text_overflow += 1
            if _has_emoji(text):
                has_emoji = True

        if el_type == "picture" and el.get("name"):
            has_icon = True

        fill = el.get("fill") or {}
        color = fill.get("color", "")
        if color and style_colors and color.upper() not in style_colors:
            score.color_mismatches += 1

    if has_emoji and has_icon:
        score.emoji_icon_conflict = True

    for i, e1 in enumerate(elements):
        for e2 in elements[i + 1:]:
            if e1.get("type") == "shape" and e2.get("type") == "shape":
                continue
            if _iou(e1, e2) > 0.3:
                score.overlaps += 1

    return score


def _iou(e1: dict, e2: dict) -> float:
    p1, p2 = e1.get("position") or {}, e2.get("position") or {}
    l1, t1 = p1.get("left") or 0, p1.get("top") or 0
    r1, b1 = l1 + (p1.get("width") or 0), t1 + (p1.get("height") or 0)
    l2, t2 = p2.get("left") or 0, p2.get("top") or 0
    r2, b2 = l2 + (p2.get("width") or 0), t2 + (p2.get("height") or 0)
    inter_w = max(0, min(r1, r2) - max(l1, l2))
    inter_h = max(0, min(b1, b2) - max(t1, t2))
    inter = inter_w * inter_h
    a1 = (p1.get("width") or 0) * (p1.get("height") or 0)
    a2 = (p2.get("width") or 0) * (p2.get("height") or 0)
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0


def _has_emoji(text: str) -> bool:
    if not isinstance(text, str):
        return False
    for ch in text:
        cp = ord(ch)
        if 0x1F300 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF:
            return True
    return False


def _extract_colors(colors_json: dict) -> list[str]:
    """Extract all hex color values from a style's colors_json."""
    out = []
    for v in colors_json.values():
        if isinstance(v, str) and len(v) in (3, 6, 8):
            out.append(v.upper().lstrip("#"))
    return out
