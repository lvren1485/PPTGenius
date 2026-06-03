"""Phase 2 Dispatcher — parallel slide processing with concurrency limit.

Fans out per-slide super_freedom agent calls across all slides. Each slide
gets its own DB session. Concurrency bounded by asyncio.Semaphore.

The dispatcher is pure code (no LLM) — single node, no loopback.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pptgenius.infrastructure.db import Database, get_session_manager
from pptgenius.infrastructure.utils import get_logger

from ..state import PPTState
from .supervisor import Phase2Timing

_log = get_logger("pptgenius.agent.ppt.dispatcher")

# Number of slides processed concurrently
_MAX_CONCURRENT_SLIDES = 5


async def dispatcher_node(state: PPTState, config) -> dict:
    """Process all slides in parallel (bounded by semaphore).

    Each slide gets its own DB session via SessionManager for the
    slide-level DB operations (notes, status update).
    """
    db: Database = config["configurable"]["db"]
    sm = get_session_manager()
    timing = Phase2Timing(total_start=time.monotonic())

    slides: list[dict] = state["outline_slides"]
    total = state["total_slides"]

    if total == 0:
        _log.warning("No slides to process")
        return {}

    # Sync style selections to all presentation_slides (set after slide creation)
    cs_id = state.get("color_scheme_id")
    tpl_id = state.get("template_id")
    if cs_id and tpl_id:
        try:
            updated = await db.update_slides_style(
                state["presentation_id"], color_scheme_id=cs_id, template_id=tpl_id,
            )
            _log.info("Synced style (cs=%d, tpl=%d) to %d slides", cs_id, tpl_id, updated or 0)
        except Exception as exc:
            _log.warning("Failed to sync slides style: %s", exc)

    _log.info("Dispatcher: %d slides, concurrency=%d", total, _MAX_CONCURRENT_SLIDES)

    # Event queue for real-time SSE streaming from parallel tasks
    event_queue: asyncio.Queue = asyncio.Queue()

    async def _emit_events():
        """Forward queued events to LangGraph stream writer (runs in graph context)."""
        try:
            writer = get_stream_writer()
        except RuntimeError:
            return
        while True:
            event = await event_queue.get()
            if event is None:  # sentinel
                break
            writer(event)

    emitter_task = asyncio.create_task(_emit_events())

    sem = asyncio.Semaphore(_MAX_CONCURRENT_SLIDES)

    async def _process_one(slide: dict) -> dict | None:
        """Process one slide through super_freedom pipeline.
        Each slide gets its OWN DB session to avoid concurrent-access corruption."""
        async with sem:
            slide_index = slide["slide_index"]
            _log.info("Dispatching slide %d/%d: %s", slide_index + 1, total,
                      slide.get("title", "?")[:40])

            await event_queue.put({
                "type": "slide_start",
                "slide_index": slide_index,
                "total": total,
                "title": slide.get("title", ""),
            })

            slide_db = sm.new_session()
            t0 = time.monotonic()
            try:
                result = await _process_super_freedom_slide(
                    db=slide_db, slide=slide, all_slides=slides,
                    state=state, config=config,
                )
                elapsed = time.monotonic() - t0
                _log.info("Slide %d/%d done in %.1fs %s",
                          slide_index + 1, total, elapsed,
                          "ERROR" if result.get("has_error") else "OK")

                await event_queue.put({
                    "type": "slide_end",
                    "slide_index": slide_index,
                    "total": total,
                    "elapsed": round(elapsed, 2),
                    "ok": not result.get("has_error"),
                })

                return result
            except Exception as exc:
                elapsed = time.monotonic() - t0
                _log.error("Slide %d/%d crashed in %.1fs: %s",
                           slide_index + 1, total, elapsed, exc)
                await event_queue.put({
                    "type": "slide_end",
                    "slide_index": slide_index,
                    "total": total,
                    "elapsed": round(elapsed, 2),
                    "ok": False,
                })
                return {"slide_index": slide_index, "elapsed": elapsed,
                        "has_error": True, "error": str(exc)}
            finally:
                await sm.close(slide_db)

    # Fan out all slides (semaphore limits actual concurrency)
    tasks = [_process_one(s) for s in slides]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Stop the event emitter
    await event_queue.put(None)
    await emitter_task

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


async def _process_super_freedom_slide(
    *,
    db: Database,
    slide: dict,
    all_slides: list[dict],
    state: PPTState,
    config,
) -> dict:
    """Process one slide in Super-Freedom mode — full creative control."""
    from ..phase2_super_freedom.agent import run_super_freedom_agent

    slide_index = slide["slide_index"]
    neighbor_ctx = _build_neighbor_context(all_slides, slide_index)
    enriched_slide = {**slide, "_neighbor_context": neighbor_ctx}

    t0 = time.monotonic()
    try:
        submitted = await run_super_freedom_agent(
            db=db, slide=enriched_slide,
            selected_layouts=state.get("selected_layouts", {}),
            presentation_id=state["presentation_id"],
            slide_index=slide_index,
            color_scheme_id=state.get("color_scheme_id"),
            conv_id=state["conversation_id"],
            config=config,
        )
        status = "completed" if submitted else "error"
        if not submitted:
            _log.error("SuperFreedom slide %d: submit_slide_instruction was never called", slide_index)
        await db.update_slide_status(
            state["presentation_id"], slide_index, status,
            error_message="" if submitted else "submit_slide_instruction was never called",
        )
        return {"slide_index": slide_index, "elapsed": time.monotonic() - t0,
                "agent_times": {"super_freedom": time.monotonic() - t0},
                "has_error": not submitted}
    except Exception as exc:
        _log.error("SuperFreedom slide %d failed: %s", slide_index, exc)
        try:
            await db.update_slide_status(
                state["presentation_id"], slide_index, "error",
                error_message=str(exc)[:500],
            )
        except Exception:
            pass
        return {"slide_index": slide_index, "elapsed": time.monotonic() - t0,
                "agent_times": {}, "has_error": True}
