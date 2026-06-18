"""SSE streaming chat endpoint — single entry point for all user messages.

Routes user messages to the Unified Master Agent.
"""

from __future__ import annotations

import json
import time
from typing import AsyncGenerator

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


@router.post("/send")
async def chat_send(
    req: ChatSendRequest,
    request: Request,
    db: Database = Depends(get_db),
) -> StreamingResponse:
    """Send a user message and receive SSE stream of agent progress."""

    conv = await db.get_conversation(req.conversation_id)
    if conv is None:
        return StreamingResponse(
            iter([_sse("error", {"code": 40001, "message": "conversation not found", "retryable": False})]),
            media_type="text/event-stream",
        )

    # Save user message
    await db.create_human_message(req.conversation_id, req.message)

    async def event_stream() -> AsyncGenerator[str, None]:
        t0 = time.time()
        try:
            yield _sse("message", {"type": "master_start", "content": req.message})

            result = await run_master_agent(db, req.conversation_id, req.message)

            yield _sse("message", {
                "type": "master_reply",
                "reply": result["reply"],
                "outline_changed": result["outline_changed"],
                "presentation_changed": result["presentation_changed"],
            })

            elapsed = round(time.time() - t0, 2)
            yield _sse("done", {
                "estimated_cost": round(conv.estimated_cost or 0, 4),
                "elapsed_seconds": elapsed,
            })
        except Exception as exc:
            _log.warning("agent error conv=%d: %s", req.conversation_id, exc)
            _log.debug("agent error detail", exc_info=True)
            yield _sse("error", {"code": 40200, "message": str(exc), "retryable": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
