"""Phase 2 Supervisor (Freedom mode) — one FreedomAgent per slide generates all elements.

The FreedomAgent receives ALL instruction files plus the full outline slide data
and generates every element (textbox, chart, table, shape, picture) at once.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

from langgraph.config import get_stream_writer

from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.layout_resolver import (
    get_container_bounds,
    select_layout,
)
from ..state import PPTState
from .freedom_agent import run_freedom_agent

_log = get_logger("pptgenius.agent.ppt.freedom_supervisor")


@dataclass
class FreedomTiming:
    total_start: float = 0.0
    total_end: float = 0.0
    slide_times: list[float] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        return self.total_end - self.total_start

    def to_dict(self) -> dict:
        return {
            "total_seconds": round(self.total_seconds, 2),
            "slide_count": len(self.slide_times),
            "slide_times": [round(t, 2) for t in self.slide_times],
        }


async def freedom_supervisor_node(state: PPTState, config) -> dict:
    """Phase 2 Freedom mode: one agent per slide, all slides in parallel."""
    db: Database = config["configurable"]["db"]
    timing = FreedomTiming(total_start=time.monotonic())

    try:
        writer = get_stream_writer()
    except RuntimeError:
        writer = lambda _: None

    presentation_id = state["presentation_id"]
    slides = state["outline_slides"]
    total = state["total_slides"]
    current = state["current_slide_index"]

    if current >= total:
        return {}

    slide = slides[current]
    slide_index = slide["slide_index"]
    layout_name = select_layout(slide)

    selected_layouts = state.get("selected_layouts", {})
    layout_def = selected_layouts.get(layout_name, {})
    container_bounds = get_container_bounds(layout_def)

    _log.info(
        "Freedom: slide %d/%d (%s) layout=%s",
        current + 1, total, slide.get("title", "?"), layout_name,
    )

    writer({
        "type": "slide_start",
        "slide_index": current,
        "total": total,
        "title": slide.get("title", ""),
        "layout": layout_name,
        "mode": "freedom",
    })

    slide_start = time.monotonic()

    try:
        await run_freedom_agent(
            db=db,
            slide=slide,
            layout_name=layout_name,
            container_bounds=container_bounds,
            presentation_id=presentation_id,
            slide_index=slide_index,
            color_scheme_id=state.get("color_scheme_id"),
            conv_id=state["conversation_id"],
            config=config,
        )
    except Exception as exc:
        _log.error("FreedomAgent failed on slide %d: %s", current, exc)

    slide_elapsed = time.monotonic() - slide_start
    timing.slide_times.append(slide_elapsed)

    writer({
        "type": "slide_end",
        "slide_index": current,
        "elapsed": round(slide_elapsed, 2),
        "mode": "freedom",
    })

    timing.total_end = time.monotonic()
    next_index = current + 1

    return {
        "current_slide_index": next_index,
        "messages": [],
    }
