"""Phase 2 per-slide processor (Sub-Agent mode) — parallel sub-agent dispatch.

Each sub-agent gets its own independent DB session via SessionManager,
so they can run concurrently within a slide without session conflicts.

process_single_slide() is called by the Dispatcher for each slide in parallel.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from langgraph.config import get_stream_writer

from pptgenius.infrastructure.db import Database, get_session_manager
from pptgenius.infrastructure.utils import get_logger

from ..common.layout_resolver import (
    get_container_bounds,
    select_layout,
)
from .text_agent import run_text_agent
from .chart_agent import run_chart_agent
from .shape_agent import run_shape_agent

_log = get_logger("pptgenius.agent.ppt.supervisor")


@dataclass
class Phase2Timing:
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


def _build_neighbor_context(all_slides: list[dict], slide_index: int, window: int = 2) -> str:
    """Build a context string from neighboring slides (1-2 before/after)."""
    parts = []
    for i in range(max(0, slide_index - window), slide_index):
        s = all_slides[i]
        parts.append(f"前{i - slide_index}页: \"{s.get('title', '')}\" "
                     f"(layout={s.get('layout_type', 'content')})")
    for i in range(slide_index + 1, min(len(all_slides), slide_index + window + 1)):
        s = all_slides[i]
        parts.append(f"后{i - slide_index}页: \"{s.get('title', '')}\" "
                     f"(layout={s.get('layout_type', 'content')})")
    return "\n".join(parts) if parts else "（独立页面，无相邻页）"


async def process_single_slide(
    *,
    db: Database,
    slide: dict,
    all_slides: list[dict],
    selected_layouts: dict[str, dict],
    presentation_id: int,
    color_scheme_id: int | None,
    template_id: int | None,
    conv_id: int,
    config,
    sm,
) -> dict:
    """Process ONE slide: determine agents, dispatch in parallel, store results.

    Returns timing dict for this slide.
    """
    slide_index = slide["slide_index"]
    layout_name = select_layout(slide)
    layout_def = selected_layouts.get(layout_name, {})
    container_bounds = get_container_bounds(layout_def)

    agents_needed = _determine_agents(slide, layout_name)
    neighbor_ctx = _build_neighbor_context(all_slides, slide_index)

    _log.info(
        "Slide %d (%s): layout=%s, agents=%s",
        slide_index + 1, slide.get("title", "?"), layout_name, agents_needed,
    )

    # Emit slide_start SSE
    try:
        writer = get_stream_writer()
        writer({
            "type": "slide_start", "slide_index": slide_index, "total": len(all_slides),
            "title": slide.get("title", ""), "layout": layout_name,
            "agents": agents_needed,
        })
    except RuntimeError:
        pass

    # Store outline notes
    outline_notes = slide.get("notes", "") or ""
    if outline_notes:
        try:
            await db.set_slide_agent_output(
                presentation_id=presentation_id, slide_index=slide_index,
                agent_type="_notes", output={"notes": outline_notes},
            )
        except Exception:
            pass

    # Enrich slide with neighbor context for sub-agents
    enriched_slide = {**slide, "_neighbor_context": neighbor_ctx}

    # ---- parallel sub-agent dispatch ----
    slide_start = time.monotonic()
    tasks = []
    agent_names: list[str] = []

    base_kwargs = dict(
        sm=sm, slide=enriched_slide, container_bounds=container_bounds,
        presentation_id=presentation_id, slide_index=slide_index,
        color_scheme_id=color_scheme_id, conv_id=conv_id, config=config,
    )

    if "text" in agents_needed:
        agent_names.append("text")
        tasks.append(_run_agent_with_session(
            run_text_agent, "text", layout_name=layout_name, **base_kwargs,
        ))
    if "chart" in agents_needed:
        agent_names.append("chart")
        tasks.append(_run_agent_with_session(
            run_chart_agent, "chart", **base_kwargs,
        ))
    if "shape" in agents_needed:
        agent_names.append("shape")
        tasks.append(_run_agent_with_session(
            run_shape_agent, "shape", layout_name=layout_name, **base_kwargs,
        ))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    slide_elapsed = time.monotonic() - slide_start
    agent_times: dict[str, float] = {}
    has_error = False

    for i, name in enumerate(agent_names):
        result = results[i] if i < len(results) else (name, 0, RuntimeError("missing"))
        if isinstance(result, Exception):
            result = (name, 0, result)

        a_name, elapsed, exc = result
        agent_times[a_name] = elapsed
        if exc:
            has_error = True
            _log.error("Agent %s failed on slide %d: %s", a_name, slide_index, exc)

    # Update slide status
    if has_error:
        try:
            await db.update_slide_status(
                presentation_id, slide_index, "error",
                error_message="One or more agents failed",
            )
        except Exception:
            pass
    else:
        try:
            await db.update_slide_status(presentation_id, slide_index, "completed")
        except Exception:
            pass

    # Emit slide_end SSE
    try:
        writer = get_stream_writer()
        writer({
            "type": "slide_end", "slide_index": slide_index,
            "elapsed": round(slide_elapsed, 2),
            "agents": agent_times,
        })
    except RuntimeError:
        pass

    return {
        "slide_index": slide_index,
        "elapsed": slide_elapsed,
        "agent_times": agent_times,
        "has_error": has_error,
    }


def _determine_agents(slide: dict, layout_name: str) -> list[str]:
    agents = ["text", "shape"]  # every slide needs text + decorations
    if slide.get("has_chart", False):
        agents.append("chart")
    return agents


async def _run_agent_with_session(run_fn, agent_name: str, sm, layout_name=None, **kwargs):
    """Run a sub-agent with its own isolated DB session, return (name, elapsed, exc)."""
    sub_db = sm.new_session()
    t0 = time.monotonic()
    try:
        extra = {}
        if layout_name is not None and agent_name in ("text", "shape"):
            extra["layout_name"] = layout_name
        await run_fn(db=sub_db, **kwargs, **extra)
        return (agent_name, time.monotonic() - t0, None)
    except Exception as exc:
        return (agent_name, time.monotonic() - t0, exc)
    finally:
        await sm.close(sub_db)
