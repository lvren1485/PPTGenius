"""Outline content generator — fills content_json for existing slides only."""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.db.engine import get_session_manager
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.model_builder import build_llm
from .knowledge_tools import (
    make_fetch_web,
    make_read_file,
    make_search_knowledge,
    make_search_web,
)
from .prompts import build_generator_system_prompt, build_generator_user_prompt

_log = get_logger("pptgenius.agent.outline.generator")

_FLAGS = ("待合并", "待分割", "待填充", "新页", "待修改")


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


# ── write tool (overwrite only, no create/delete) ─────────────────────────────


def _make_write_slides(db: Database, outline_id: int, section_id: int):
    _called: list[bool] = [False]

    @tool
    async def write_slides(
        slides: list[dict],
        citations: list[dict] | None = None,
    ) -> str:
        """Overwrite content for existing section slides. MUST be called last.

        Only fills content_json / has_image / has_chart / notes on pre-created
        slides. Does NOT create or delete slides. Target slides by slide_index.

        Parameters
        ----------
        slides : list[dict] — [{slide_index, title, content_json, has_image, has_chart, notes}, ...]. title is REQUIRED — provides a clean, descriptive title (flag tags like 待修改 are stripped).
        citations : list[dict] | None — [{chunk_id, reason}, ...], cite knowledge sources used.
        """
        existing = await db.get_slides_by_outline_id(outline_id)
        sec_slides = sorted(
            [s for s in existing if s.section_id == section_id],
            key=lambda s: s.slide_index,
        )
        index_map = {s.slide_index: s for s in sec_slides}

        # Resolve chunk_id → file_id for citations
        resolved_citations: list[dict] | None = None
        if citations:
            resolved_citations = []
            for c in citations:
                cid = c.get("chunk_id")
                if cid is None:
                    continue
                chunk = await db.get_chunk_by_id(cid)
                fid = chunk.file_id if chunk else None
                resolved_citations.append({
                    "chunk_id": cid,
                    "knowledge_file_id": fid,
                    "reason": c.get("reason", ""),
                })

        updated = 0
        for sl in slides:
            si = sl.get("slide_index")
            target = index_map.get(si)
            if target is None:
                continue
            updates: dict = {"status": "completed"}
            if "title" in sl:
                updates["title"] = sl["title"]
                updates["content_json"] = sl["content_json"]
            if "has_image" in sl:
                updates["has_image"] = sl["has_image"]
            if "has_chart" in sl:
                updates["has_chart"] = sl["has_chart"]
            if "notes" in sl:
                updates["notes"] = sl["notes"]
            await db.update_outline_slide(target.id, **updates)
            if resolved_citations:
                await db.update_outline_slide_citations(target.id, resolved_citations)
            updated += 1

        _called[0] = True
        return json.dumps({"section_id": section_id, "updated": updated,
                           "citations": len(resolved_citations) if resolved_citations else 0,
                           "status": "ok"})

    return write_slides, _called


# ── main entry ────────────────────────────────────────────────────────────────


async def run_outline_generator(
    db: Database,
    conversation_id: int,
    section_id: int,
    *,
    query: str | None = None,
    knowledge_mode: str = "auto",
) -> str:
    """Fill content for one section's pre-created slides."""
    writer = _get_writer()

    # Read section metadata from the caller's session
    section = await db.get_outline_section(section_id)
    if section is None:
        return f"错误: section {section_id} 不存在"
    outline_id = section.outline_id
    section_title = section.title

    outline = await db.get_outline(outline_id)
    conv = await db.get_conversation(conversation_id)
    user_id = conv.user_id if conv else 0
    rag_mode = await db.get_rag_mode(user_id) if user_id else "user"

    # Use an independent session for all generator work (avoids asyncmy concurrent read issue)
    sm = get_session_manager()
    gdb = None
    try:
        gdb = sm.new_session()
        kb_count = [0]
        web_count = [0]
        fetch_count = [0]
        read_count = [0]
        fetched_ids: set[int] = set()

        write_tool, was_called = _make_write_slides(gdb, outline_id, section_id)
        tools = [
            make_search_knowledge(gdb, user_id, conversation_id, rag_mode, kb_count),
            make_search_web(web_count),
            make_fetch_web(gdb, user_id, conversation_id, fetch_count),
            make_read_file(gdb, read_count, fetched_ids),
            write_tool,
        ]

        system_prompt = build_generator_system_prompt()
        user_prompt = await build_generator_user_prompt(
            db=gdb,
            outline_id=outline_id,
            section_id=section_id,
            query=query,
            knowledge_mode=knowledge_mode,
        )

        llm, agent_id, mw = build_llm(conversation_id)
        push_agent(conversation_id, agent_id)
        agent = create_agent(
            model=llm, tools=tools,
            system_prompt=system_prompt,
            middleware=[mw],
        )

        writer({"type": "outline_generator_start", "section": section_title})
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            config={"recursion_limit": 50},
        )

        if not was_called[0]:
            _log.warning("write_slides not called — retrying")
            retry_msg = HumanMessage(content="请立即调用 write_slides 工具写入内容。不要再搜索或分析，直接写入。")
            clean = _strip_dangling_tool_calls(result["messages"])
            await agent.ainvoke(
                {"messages": clean + [retry_msg]},
                config={"recursion_limit": 30},
            )

        writer({"type": "outline_generator_end", "section": section_title})
        return f"章节'{section_title}'填充完成"
    finally:
        if gdb is not None:
            await sm.close(gdb)


def _strip_dangling_tool_calls(messages: list) -> list:
    cleaned = list(messages)
    while cleaned and isinstance(cleaned[-1], AIMessage) and cleaned[-1].tool_calls:
        cleaned.pop()
    return cleaned
