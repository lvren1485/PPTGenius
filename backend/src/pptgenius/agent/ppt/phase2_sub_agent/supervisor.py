"""Phase 2 Supervisor (Sub-Agent mode) — dispatches TextAgent + ChartAgent + ShapeAgent
concurrently per slide using asyncio.gather.

Each slide is processed sequentially, but within each slide the sub-agents
run in parallel to reduce total wall-clock time.

Timing is recorded per-slide and aggregated.
"""

from __future__ import annotations

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
from .text_agent import run_text_agent
from .chart_agent import run_chart_agent
from .shape_agent import run_shape_agent

_log = get_logger("pptgenius.agent.ppt.supervisor")


@dataclass
class Phase2Timing:
    """Timing stats for Phase 2."""
    total_start: float = 0.0
    total_end: float = 0.0
    slide_times: list[float] = field(default_factory=list)
    agent_times: dict[str, list[float]] = field(default_factory=dict)

    @property
    def total_seconds(self) -> float:
        return self.total_end - self.total_start

    def to_dict(self) -> dict:
        return {
            "total_seconds": round(self.total_seconds, 2),
            "slide_count": len(self.slide_times),
            "slide_times": [round(t, 2) for t in self.slide_times],
            "agent_times": {
                k: [round(t, 2) for t in v] for k, v in self.agent_times.items()
            },
        }


async def supervisor_node(state: PPTState, config) -> dict:
    """Phase 2 Supervisor: iterate slides, dispatch sub-agents concurrently per slide."""
    db: Database = config["configurable"]["db"]
    timing = Phase2Timing(total_start=time.monotonic())

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

    # Get the current slide
    slide = slides[current]
    slide_index = slide["slide_index"]
    layout_name = select_layout(slide)

    # Load layout and color scheme for context
    selected_layouts = state.get("selected_layouts", {})
    layout_def = selected_layouts.get(layout_name, {})
    container_bounds = get_container_bounds(layout_def)

    # Determine which agents are needed
    agents_needed = _determine_agents(slide, layout_name)
    _log.info(
        "Slide %d/%d (%s): layout=%s, agents=%s",
        current + 1, total, slide.get("title", "?"), layout_name, agents_needed,
    )

    # Ensure presentation_slide exists (check first to avoid duplicates)
    existing_slides = await db.get_slides_by_presentation_id(presentation_id)
    if not any(s.slide_index == slide_index for s in existing_slides):
        await db.create_presentation_slide(
            presentation_id=presentation_id,
            slide_index=slide_index,
            layout_name=layout_name,
            color_scheme_id=state.get("color_scheme_id"),
            template_id=state.get("template_id"),
        )

    # Store outline slide notes for assembly (写入PPT演讲者备注)
    outline_notes = slide.get("notes", "") or ""
    if outline_notes:
        try:
            await db.set_slide_agent_output(
                presentation_id=presentation_id,
                slide_index=slide_index,
                agent_type="_notes",
                output={"notes": outline_notes},
            )
        except Exception:
            pass  # slide may not exist yet or notes already stored

    writer({
        "type": "slide_start",
        "slide_index": current,
        "total": total,
        "title": slide.get("title", ""),
        "layout": layout_name,
        "agents": agents_needed,
    })

    # ---- sequential sub-agent dispatch (sequential to avoid DB session conflicts) ----
    slide_start = time.monotonic()
    results: list[tuple[str, float, Exception | None]] = []

    for agent_name in agents_needed:
        writer({"type": "agent_start", "agent": agent_name, "slide_index": current})
        _log.info("Slide %d: starting %s_agent", current, agent_name)

        fn = {"text": run_text_agent, "chart": run_chart_agent, "shape": run_shape_agent}[agent_name]
        kwargs = dict(
            db=db, slide=slide, container_bounds=container_bounds,
            presentation_id=presentation_id, slide_index=slide_index,
            color_scheme_id=state.get("color_scheme_id"),
            conv_id=state["conversation_id"], config=config,
        )
        if agent_name == "text":
            kwargs["layout_name"] = layout_name
        elif agent_name == "shape":
            kwargs["layout_name"] = layout_name

        result = await _run_with_timing(fn, **kwargs)
        results.append(result)

        name, elapsed, exc = result
        writer({"type": "agent_end", "agent": agent_name,
                "elapsed": round(elapsed, 2),
                "ok": exc is None})
        _log.info("Slide %d: %s_agent done in %.1fs (err=%s)", current, agent_name, elapsed, exc)

    slide_elapsed = time.monotonic() - slide_start
    timing.slide_times.append(slide_elapsed)

    for agent_name, agent_time, exc in results:
        if agent_name not in timing.agent_times:
            timing.agent_times[agent_name] = []
        timing.agent_times[agent_name].append(agent_time)
        if exc:
            _log.error("Agent %s failed on slide %d: %s", agent_name, current, exc)

    writer({
        "type": "slide_end",
        "slide_index": current,
        "elapsed": round(slide_elapsed, 2),
    })

    timing.total_end = time.monotonic()
    next_index = current + 1

    return {
        "current_slide_index": next_index,
        "messages": [],  # each sub-agent manages its own messages
    }


def _determine_agents(slide: dict, layout_name: str) -> list[str]:
    """Determine which agents are needed for this slide."""
    agents = ["text"]  # always need text

    has_chart = slide.get("has_chart", False)
    if has_chart:
        agents.append("chart")

    # Shape agent needed for decorative pages
    if layout_name in ("title_slide", "section", "ending"):
        agents.append("shape")

    return agents


async def _run_with_timing(run_fn, **kwargs) -> tuple[str, float, Exception | None]:
    """Run a sub-agent and return (agent_name, elapsed_seconds, exception_or_none)."""
    agent_name = run_fn.__name__.replace("run_", "")
    t0 = time.monotonic()
    try:
        await run_fn(**kwargs)
        return (agent_name, time.monotonic() - t0, None)
    except Exception as exc:
        return (agent_name, time.monotonic() - t0, exc)
