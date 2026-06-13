"""Outline content generator — fills content_json for existing slides only."""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.model_builder import build_llm
from .knowledge_tools import (
    make_fetch_web,
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
        slides : list[dict] — [{slide_index, title, content_json, has_image, has_chart, notes}, ...]. title is REQUIRED.
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
            if "content_json" in sl:
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

    section = await db.get_outline_section(section_id)
    if section is None:
        return f"错误: section {section_id} 不存在"
    outline_id = section.outline_id
    section_title = section.title

    outline = await db.get_outline(outline_id)
    conv = await db.get_conversation(conversation_id)
    user_id = conv.user_id if conv else 0
    rag_mode = await db.get_rag_mode(user_id) if user_id else "user"

    kb_count = [0]
    web_count = [0]
    fetch_count = [0]

    write_tool, was_called = _make_write_slides(db, outline_id, section_id)
    tools = [
        write_tool,
        make_search_knowledge(db, user_id, conversation_id, rag_mode, kb_count),
        make_search_web(web_count),
        make_fetch_web(db, user_id, conversation_id, fetch_count),
    ]

    system_prompt = build_generator_system_prompt()
    user_prompt = await build_generator_user_prompt(
        db=db,
        outline_id=outline_id,
        section_id=section_id,
        query=query,
        knowledge_mode=knowledge_mode,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    llm, agent_id, mw = build_llm(conversation_id)
    push_agent(conversation_id, agent_id)
    agent = create_agent(
        model=llm, tools=tools,
        system_prompt=system_prompt,
        middleware=[mw],
    )

    writer({"type": "outline_generator_start", "section": section_title})

    # ── first attempt ──
    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            config={"recursion_limit": 80},
        )
    except Exception:
        _log.warning("generator failed section=%d — retrying with clean state", section_id)
        result = {"messages": [HumanMessage(content=user_prompt)]}

    if not was_called[0]:
        _log.warning("write_slides not called section=%d — retrying", section_id)
        # Collect ALL tool results into one string, discard all AIMessages/thinking
        tool_texts: list[str] = []
        for m in result.get("messages", []):
            if isinstance(m, ToolMessage) and m.content:
                name = getattr(m, "name", "tool")
                tool_texts.append(f"### [{name}]\n{str(m.content)}")
        gathered = "\n\n---\n\n".join(tool_texts) if tool_texts else "（无知识搜索结果）"

        # Build fresh user prompt + retry instruction
        retry_user = await build_generator_user_prompt(
            db=db, outline_id=outline_id, section_id=section_id,
            query=query, knowledge_mode=knowledge_mode,
            user_id=user_id, conversation_id=conversation_id,
        )
        retry_content = f"{retry_user}\n\n## 已收集的知识\n{gathered}\n\n---\n⚠️ 以上知识已足够。请**立即**调用 write_slides 写入内容。"

        # New agent with only write_slides — no search tools
        retry_agent = create_agent(
            model=llm, tools=[write_tool],
            system_prompt=system_prompt,
            middleware=[mw],
        )
        retry_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=retry_content),
        ]
        try:
            await retry_agent.ainvoke(
                {"messages": retry_messages},
                config={"recursion_limit": 15},
            )
        except Exception:
            _log.warning("generator retry failed section=%d — giving up", section_id)

    if not was_called[0]:
        _log.error("generator could not write slides section=%d", section_id)
        return f"错误: 章节'{section_title}'填充失败"

    writer({"type": "outline_generator_end", "section": section_title})
    return f"章节'{section_title}'填充完成"
