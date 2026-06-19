"""SSE streaming chat endpoint — with cancel support and disconnect handling."""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from pptgenius.agent.master import run_master_agent
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

from .deps import get_db
from .schemas import ChatSendRequest

_log = get_logger("pptgenius.api.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Cancel Registry ────────────────────────────────────────────────────

class CancelRegistry:
    _tasks: dict[int, asyncio.Task] = {}

    @classmethod
    def register(cls, conv_id: int, task: asyncio.Task) -> None:
        cls._tasks[conv_id] = task

    @classmethod
    def cancel(cls, conv_id: int) -> None:
        t = cls._tasks.get(conv_id)
        if t and not t.done():
            t.cancel()

    @classmethod
    def unregister(cls, conv_id: int) -> None:
        cls._tasks.pop(conv_id, None)


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post("/send")
async def chat_send(
    req: ChatSendRequest,
    request: Request,
    db: Database = Depends(get_db),
) -> StreamingResponse:
    conv = await db.get_conversation(req.conversation_id)
    if conv is None:
        return StreamingResponse(
            iter([_sse("error", {"code": 40001, "message": "conversation not found", "retryable": False})]),
            media_type="text/event-stream",
        )

    await db.create_human_message(req.conversation_id, req.message)
    conv_id = req.conversation_id

    async def event_stream():
        t0 = time.time()
        task = asyncio.create_task(run_master_agent(db, conv_id, req.message))
        CancelRegistry.register(conv_id, task)
        last_hb = time.monotonic()

        try:
            yield _sse("message", {"type": "master_start"})

            while not task.done():
                # heartbeat
                now = time.monotonic()
                if now - last_hb > 5:
                    yield _sse("message", {"type": "heartbeat"})
                    last_hb = now

                if await request.is_disconnected():
                    CancelRegistry.cancel(conv_id)
                    break

                await asyncio.sleep(1)

            # ── normal (cancel handled inside master) ──
            result = await task
            yield _sse("message", {
                "type": "master_reply",
                "reply": result["reply"],
                "outline_changed": result.get("outline_changed", False),
                "presentation_changed": result.get("presentation_changed", False),
            })
            if result.get("outline_snapshot_id"):
                yield _sse("message", {
                    "type": "outline_snapshot",
                    "snapshot_id": result["outline_snapshot_id"],
                })
            if result.get("presentation_snapshot_id"):
                yield _sse("message", {
                    "type": "presentation_snapshot",
                    "snapshot_id": result["presentation_snapshot_id"],
                })
            elapsed = round(time.time() - t0, 2)
            yield _sse("done", {
                "estimated_cost": round(conv.estimated_cost or 0, 4),
                "elapsed_seconds": elapsed,
            })

        except asyncio.CancelledError:
            CancelRegistry.cancel(conv_id)
            raise  # must re-raise for Starlette teardown

        except Exception as exc:
            _log.warning("agent error conv=%d: %s", conv_id, exc)
            _log.debug("agent error detail", exc_info=True)
            yield _sse("error", {"code": 40200, "message": str(exc), "retryable": True})

        finally:
            CancelRegistry.unregister(conv_id)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{conversation_id}/cancel")
async def cancel_agent(conversation_id: int):
    CancelRegistry.cancel(conversation_id)
    return {"status": "ok"}
