"""Phase 2 Dispatcher — parallel slide processing with concurrency limit.

Fans out process_single_slide() calls across all slides. Each slide
processes its sub-agents (text/chart/shape) in parallel internally.

The dispatcher is pure code (no LLM) — single node, no loopback.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pptgenius.infrastructure.db import Database, get_session_manager
from pptgenius.infrastructure.utils import get_logger

from ..common.layout_resolver import select_layout
from ..state import PPTState
from .supervisor import Phase2Timing, process_single_slide

_log = get_logger("pptgenius.agent.ppt.dispatcher")

# Number of slides processed concurrently
_MAX_CONCURRENT_SLIDES = 5


async def dispatcher_node(state: PPTState, config) -> dict:
    """Process all slides in parallel (bounded by semaphore).

    Each slide gets its own DB session via SessionManager for the
    slide-level DB operations (notes, status update). Sub-agents within
    a slide further get their own isolated sessions.
    """
    db: Database = config["configurable"]["db"]
    sm = get_session_manager()
    timing = Phase2Timing(total_start=time.monotonic())

    slides: list[dict] = state["outline_slides"]
    total = state["total_slides"]
    mode: str = state.get("ppt_mode", "sub_agent")

    if total == 0:
        _log.warning("No slides to process")
        return {}

    _log.info("Dispatcher: %d slides, mode=%s, concurrency=%d",
              total, mode, _MAX_CONCURRENT_SLIDES)

    sem = asyncio.Semaphore(_MAX_CONCURRENT_SLIDES)

    async def _process_one(slide: dict) -> dict | None:
        """Process one slide through the appropriate mode pipeline."""
        async with sem:
            slide_index = slide["slide_index"]
            _log.info("Dispatching slide %d/%d: %s", slide_index + 1, total,
                      slide.get("title", "?")[:40])

            t0 = time.monotonic()
            try:
                result: dict[str, Any]
                if mode == "freedom":
                    result = await _process_freedom_slide(
                        db=db, sm=sm, slide=slide, all_slides=slides,
                        state=state, config=config,
                    )
                else:
                    result = await process_single_slide(
                        db=db, sm=sm, slide=slide, all_slides=slides,
                        selected_layouts=state.get("selected_layouts", {}),
                        presentation_id=state["presentation_id"],
                        color_scheme_id=state.get("color_scheme_id"),
                        template_id=state.get("template_id"),
                        conv_id=state["conversation_id"],
                        config=config,
                    )
                elapsed = time.monotonic() - t0
                _log.info("Slide %d/%d done in %.1fs %s",
                          slide_index + 1, total, elapsed,
                          "ERROR" if result.get("has_error") else "OK")
                return result
            except Exception as exc:
                elapsed = time.monotonic() - t0
                _log.error("Slide %d/%d crashed in %.1fs: %s",
                           slide_index + 1, total, elapsed, exc)
                return {"slide_index": slide_index, "elapsed": elapsed,
                        "has_error": True, "error": str(exc)}

    # Fan out all slides (semaphore limits actual concurrency)
    tasks = [_process_one(s) for s in slides]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect timing
    ok = 0
    for r in results:
        if isinstance(r, Exception):
            _log.error("Dispatcher gather exception: %s", r)
            continue
        if r is None:
            continue
        timing.slide_times.append(r.get("elapsed", 0))
        agent_times = r.get("agent_times", {})
        for a_name, a_elapsed in agent_times.items():
            if a_name not in timing.agent_times:
                timing.agent_times[a_name] = []
            timing.agent_times[a_name].append(a_elapsed)
        if not r.get("has_error"):
            ok += 1

    timing.total_end = time.monotonic()
    _log.info("Dispatcher done: %d/%d slides OK in %.1fs (timing=%s)",
              ok, total, timing.total_seconds, timing.to_dict())

    return {
        "design_rationales": [],
        "messages": [],
    }


def _build_neighbor_context(all_slides: list[dict], slide_index: int, window: int = 2) -> str:
    """Build a context string from neighboring slides."""
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


async def _process_freedom_slide(
    *,
    db: Database,
    sm,
    slide: dict,
    all_slides: list[dict],
    state: PPTState,
    config,
) -> dict:
    """Process one slide in Freedom mode (single agent generates everything)."""
    from ..phase2_freedom.freedom_agent import run_freedom_agent

    slide_index = slide["slide_index"]
    layout_name = select_layout(slide)

    selected_layouts = state.get("selected_layouts", {})
    layout_def = selected_layouts.get(layout_name, {})
    from ..common.layout_resolver import get_container_bounds
    container_bounds = get_container_bounds(layout_def)

    neighbor_ctx = _build_neighbor_context(all_slides, slide_index)
    enriched_slide = {**slide, "_neighbor_context": neighbor_ctx}

    # Create presentation_slide if needed (freedom mode may not pre-create)
    existing = await db.get_slides_by_presentation_id(state["presentation_id"])
    if not any(s.slide_index == slide_index for s in existing):
        await db.create_presentation_slide(
            presentation_id=state["presentation_id"],
            slide_index=slide_index,
            layout_name=layout_name,
            color_scheme_id=state.get("color_scheme_id"),
            template_id=state.get("template_id"),
        )

    t0 = time.monotonic()
    try:
        await run_freedom_agent(
            db=db, slide=enriched_slide, layout_name=layout_name,
            container_bounds=container_bounds,
            presentation_id=state["presentation_id"],
            slide_index=slide_index,
            color_scheme_id=state.get("color_scheme_id"),
            conv_id=state["conversation_id"],
            config=config,
        )
        await db.update_slide_status(state["presentation_id"], slide_index, "completed")
        return {"slide_index": slide_index, "elapsed": time.monotonic() - t0,
                "agent_times": {"freedom": time.monotonic() - t0}, "has_error": False}
    except Exception as exc:
        _log.error("Freedom slide %d failed: %s", slide_index, exc)
        try:
            await db.update_slide_status(
                state["presentation_id"], slide_index, "error",
                error_message=str(exc)[:500],
            )
        except Exception:
            pass
        return {"slide_index": slide_index, "elapsed": time.monotonic() - t0,
                "agent_times": {}, "has_error": True}
