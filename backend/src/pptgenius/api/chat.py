"""SSE streaming chat endpoint — single entry point for all user messages.

Agent supervisor decides what to do based on current conversation phase.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils.logger import get_logger

from .deps import get_db, get_knowledge_manager, get_web_search_service, get_workspace_manager
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
            yield _sse("done", {
                "estimated_cost": round(conv.estimated_cost or 0, 4),
                "elapsed_seconds": elapsed,
            })
        except Exception as exc:
            _log.exception("agent error")
            yield _sse("error", {"code": 40200, "message": str(exc), "retryable": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _run_agent(req: ChatSendRequest, db: Database) -> AsyncGenerator[str, None]:
    """Agent supervisor — TODO: replace with actual LangGraph agent.

    Placeholder simulates the full agent flow.
    """
    # TODO: Implement agent supervisor here.
    #   The supervisor should:
    #   1. Load conversation state (phase, messages, latest outline/presentation)
    #   2. Run BM25 RAG via KnowledgeService.search(user_id, query)
    #   3. Optionally run web search via WebSearchService.search() + fetch_and_ingest()
    #   4. Decide next action based on current_phase:
    #      - "chat" / no outline → generate outline (generator-evaluator loop)
    #      - "waiting_user" + outline exists → interpret feedback, modify outline or proceed
    #      - confirmed outline → generate PPT (supervisor-subagent pipeline)
    #      - generated PPT → interpret feedback, modify slides or regenerate
    #   5. Stream progress, outline, ppt_ready events via SSE
    #
    #   For now, emit placeholder events to demonstrate SSE plumbing.

    _log.info("TODO: agent supervisor for conv=%d msg=%r", req.conversation_id, req.message)

    yield _sse("phase", {"phase": "rag", "message": "检索知识库..."})

    # Simulate knowledge retrieval
    await asyncio.sleep(0.1)
    yield _sse("knowledge", {"sources": []})

    yield _sse("phase", {"phase": "outline", "message": "开始生成大纲..."})

    yield _sse("progress", {"step": "generating", "detail": "正在生成大纲...", "pct": 10})
    await asyncio.sleep(0.1)

    yield _sse("progress", {"step": "evaluating", "detail": "评估中...", "pct": 30})
    await asyncio.sleep(0.1)

    # Placeholder outline
    yield _sse("outline", {
        "outline_id": 0,
        "title": "大纲示例",
        "slides": [
            {"slide_index": 0, "title": "示例页", "layout_type": "title", "content_json": {}}
        ],
        "eval_score": 0.80,
    })

    yield _sse("phase", {"phase": "waiting_user", "message": "请确认大纲，或提出修改意见"})
