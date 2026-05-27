"""SSE streaming chat endpoint — single entry point for all user messages.

The coordinator agent analyses intent and dispatches to sub-agents.
"""

from __future__ import annotations

import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from pptgenius.agent import run_coordinator
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import TokenCounter, get_logger

from .deps import get_db
from .schemas import ChatSendRequest

_log = get_logger("pptgenius.api.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    """Format an SSE message."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/send")
async def chat_send(
    req: ChatSendRequest,
    request: Request,
    db: Database = Depends(get_db),
) -> StreamingResponse:
    """Send a user message and receive SSE stream of agent progress.

    The agent supervisor inspects ``conversation.current_phase`` and the latest
    outline/presentation state to decide the next action.
    """

    # Verify conversation exists
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
            async for event in _run_agent(req, db):
                if await request.is_disconnected():
                    _log.debug("client disconnected, stopping stream")
                    return
                yield event
            elapsed = round(time.time() - t0, 2)
            token_snapshot = TokenCounter.for_conversation(req.conversation_id).snapshot()
            yield _sse("done", {
                "estimated_cost": round(conv.estimated_cost or 0, 4),
                "elapsed_seconds": elapsed,
                "token_usage": token_snapshot,
            })
        except Exception as exc:
            _log.exception("agent error")
            yield _sse("error", {"code": 40200, "message": str(exc), "retryable": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _run_agent(req: ChatSendRequest, db: Database) -> AsyncGenerator[str, None]:
    """Run the coordinator agent — analyses intent and dispatches to sub-agents."""
    _log.info("coordinator start: conv=%d msg=%r", req.conversation_id, req.message)

    async for event in run_coordinator(db, req.conversation_id, req.message):
        yield event
