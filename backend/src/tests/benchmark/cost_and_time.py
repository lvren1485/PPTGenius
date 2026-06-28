"""B1: Generation time & cost — computed from messages table only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pptgenius.infrastructure.db.models import (
    Conversation, Message, Outline, Presentation,
)

_OUTLINE_MARKERS = {"explore", "gen_content"}
_PPT_MARKERS = {"ppt_style", "slides_content"}
_EVALUATOR_CTYPE = "evaluate"


@dataclass
class GenerationStats:
    conv_id: int
    conv_title: str
    gen_type: str  # "outline" | "ppt"
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: float = 0
    total_cost: float = 0
    eval_excluded_seconds: float = 0
    eval_excluded_cost: float = 0
    slide_count: int = 0
    retry_count: int = 0

    @property
    def per_slide_cost(self) -> float:
        return self.total_cost / self.slide_count if self.slide_count else 0

    @property
    def duration_display(self) -> str:
        m, s = divmod(int(self.duration_seconds), 60)
        return f"{m}m {s}s"


async def compute_cost_and_time(session: AsyncSession) -> list[GenerationStats]:
    """Scan all conversations, detect outline/PPT generation turns, compute metrics."""
    result = await session.execute(
        select(Conversation).where(Conversation.status != "deleted")
        .order_by(Conversation.id)
    )
    convs = list(result.scalars().all())
    stats: list[GenerationStats] = []

    for conv in convs:
        msg_result = await session.execute(
            select(Message).where(Message.conversation_id == conv.id)
            .order_by(Message.idx)
        )
        messages = list(msg_result.scalars().all())
        if not messages:
            continue

        turns = _split_turns(messages)
        outline_found = False
        ppt_found = False

        for turn in turns:
            ctypes = {m.content_type for m in turn if m.role == "tool_call" and m.content_type}

            if not outline_found and _OUTLINE_MARKERS.issubset(ctypes):
                s = _compute_turn_stats(conv, turn, "outline")
                s.slide_count = await _get_outline_slide_count(session, conv.id)
                s.retry_count = _count_retries(turn, "gen_content")
                stats.append(s)
                outline_found = True

            if not ppt_found and _PPT_MARKERS.issubset(ctypes):
                s = _compute_turn_stats(conv, turn, "ppt")
                s.slide_count = await _get_ppt_slide_count(session, conv.id)
                s.retry_count = _count_retries(turn, "slides_content")
                stats.append(s)
                ppt_found = True

    return _filter_outliers(stats)


def _split_turns(messages: list) -> list[list]:
    """Split messages into turns by user text messages."""
    turns: list[list] = []
    current: list = []
    for m in messages:
        if m.role == "user" and m.content_type == "text":
            if current:
                turns.append(current)
            current = [m]
        else:
            current.append(m)
    if current:
        turns.append(current)
    return turns


def _compute_turn_stats(conv, turn: list, gen_type: str) -> GenerationStats:
    """Compute time and cost for a single turn, excluding evaluator spans."""
    user_msg = next((m for m in turn if m.role == "user"), None)
    tool_results = [m for m in turn if m.role == "tool_result"]
    last_tr = tool_results[-1] if tool_results else None

    start = user_msg.created_at if user_msg else None
    end = last_tr.created_at if last_tr else None

    raw_duration = (end - start).total_seconds() if start and end else 0
    total_cost = sum(m.estimated_cost or 0 for m in turn)

    eval_seconds, eval_cost = _exclude_evaluator(turn)

    return GenerationStats(
        conv_id=conv.id,
        conv_title=conv.title or f"Conv#{conv.id}",
        gen_type=gen_type,
        start_time=start,
        end_time=end,
        duration_seconds=max(0, raw_duration - eval_seconds),
        total_cost=max(0, total_cost - eval_cost),
        eval_excluded_seconds=eval_seconds,
        eval_excluded_cost=eval_cost,
    )


def _exclude_evaluator(turn: list) -> tuple[float, float]:
    """Find evaluator tool_call/tool_result pairs and return their total time and cost."""
    eval_calls: dict[str, datetime] = {}
    excluded_seconds = 0.0
    excluded_cost = 0.0

    for m in turn:
        meta = m.metadata_json or {}
        tc_id = meta.get("tool_call_id", "")

        if m.role == "tool_call" and m.content_type == _EVALUATOR_CTYPE:
            eval_calls[tc_id] = m.created_at

        elif m.role == "tool_result" and m.content_type == _EVALUATOR_CTYPE:
            call_time = eval_calls.pop(tc_id, None)
            if call_time and m.created_at:
                excluded_seconds += (m.created_at - call_time).total_seconds()
            excluded_cost += m.estimated_cost or 0

    return excluded_seconds, excluded_cost


def _count_retries(turn: list, content_type: str) -> int:
    """Count how many times a tool was called (retries = count - 1)."""
    count = sum(1 for m in turn if m.role == "tool_call" and m.content_type == content_type)
    return max(0, count - 1)


async def _get_outline_slide_count(session: AsyncSession, conv_id: int) -> int:
    conv = await session.get(Conversation, conv_id)
    if not conv or not conv.current_outline_id:
        return 0
    outline = await session.get(Outline, conv.current_outline_id)
    return outline.slide_count or 0 if outline else 0


async def _get_ppt_slide_count(session: AsyncSession, conv_id: int) -> int:
    conv = await session.get(Conversation, conv_id)
    if not conv or not conv.current_outline_id:
        return 0
    result = await session.execute(
        select(Presentation)
        .where(Presentation.conversation_id == conv_id)
        .where(Presentation.status != "deleted")
        .order_by(Presentation.created_at.desc())
    )
    pres = result.scalars().first()
    return pres.slide_count or 0 if pres else 0


def _filter_outliers(stats: list[GenerationStats]) -> list[GenerationStats]:
    """Remove extreme data points:
    - PPT duration < 2min (incomplete/failed)
    - Outline duration > 6min (old V1 architecture)
    - PPT duration > 10min (old architecture or failures)
    """
    filtered = []
    for s in stats:
        if s.gen_type == "outline" and s.duration_seconds > 360:
            continue
        if s.gen_type == "ppt" and (s.duration_seconds < 120 or s.duration_seconds > 600):
            continue
        filtered.append(s)
    return filtered
