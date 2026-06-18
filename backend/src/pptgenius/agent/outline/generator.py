"""Outline content generator — fills content_json for existing slides only."""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.middleware import build_middlewares
from pptgenius.infrastructure.llm import create_llm
from .knowledge_tools import (
    make_fetch_web,
    make_search_knowledge,
    make_search_web,
)
from .prompts import build_generator_system_prompt, build_generator_user_prompt
from .prompts import _STATUS_HINTS

_log = get_logger("pptgenius.agent.outline.generator")


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


# ── write tools (single-slide) ──────────────────────────────────────────────────


def _make_write_tools(db: Database, outline_id: int, section_id: int):
    _written: set[int] = set()

    @tool
    async def write_slide(
        slide_index: int,
        title: str,
        content_json: dict,
        has_image: bool = False,
        has_chart: bool = False,
        notes: str = "",
        citations: list[dict] | None = None,
    ) -> str:
        """Write content for ONE slide. Call once per slide.

        Parameters
        ----------
        slide_index : int — the slide's index number.
        title : str — clean, specific title for this slide.
        content_json : dict — {main_points: [...], detailed_content: "...", key_data: "...", visual_note: "...", recommended_ppt_format: "..."}
        has_image : bool — whether the slide needs an image.
        has_chart : bool — whether the slide needs a chart.
        notes : str — speaker notes (optional).
        citations : list[dict] | None — [{chunk_id, reason}, ...] for knowledge sources used.
        """
        existing = await db.get_slides_by_outline_id(outline_id)
        sec = sorted([s for s in existing if s.section_id == section_id], key=lambda s: s.slide_index)
        index_map = {s.slide_index: s for s in sec}

        target = index_map.get(slide_index)
        if target is None:
            return f"错误: slide_index={slide_index} 不在当前章节"

        resolved: list[dict] | None = None
        if citations:
            resolved = []
            for c in citations:
                cid = c.get("chunk_id")
                if cid is None:
                    continue
                chunk = await db.get_chunk_by_id(cid)
                fid = chunk.file_id if chunk else None
                resolved.append({"chunk_id": cid, "knowledge_file_id": fid, "reason": c.get("reason", "")})

        await db.update_outline_slide(target.id,
            title=title, content_json=content_json,
            has_image=has_image, has_chart=has_chart, notes=notes,
            status="completed",
        )
        if resolved:
            await db.update_outline_slide_citations(target.id, resolved)

        _written.add(slide_index)
        remaining = [s.slide_index for s in sec if s.slide_index not in _written]
        return json.dumps({"written": slide_index, "ok": True, "remaining": remaining}, ensure_ascii=False)

    @tool
    async def pending_slides() -> str:
        """List section slides that still need content. No args. Call to see what's left."""
        slides = await db.get_slides_by_outline_id(outline_id)
        sec = sorted([s for s in slides if s.section_id == section_id], key=lambda s: s.slide_index)
        pending = []
        for s in sec:
            if s.slide_index in _written:
                continue
            cj = s.content_json
            if isinstance(cj, dict):
                has_content = bool(cj.get("main_points")) or bool(cj.get("detailed_content"))
            else:
                has_content = False
            if s.status == "completed" or has_content:
                _written.add(s.slide_index)
                continue
            st = s.status or "new"
            hint = _STATUS_HINTS.get(st, "需要填充内容")
            pending.append({
                "slide_index": s.slide_index, "title": s.title or "",
                "layout_type": s.layout_type or "content",
                "status": st, "hint": hint,
            })
        if not pending:
            return "所有幻灯片已写入。可以结束了。"
        items = "\n".join(
            f"  - slide_index={p['slide_index']}: {p['title']} ({p['layout_type']}) "
            f"[{p['status']}] — {p['hint']}"
            for p in pending
        )
        return f"待写入 ({len(pending)}页):\n{items}"

    return write_slide, pending_slides, _written


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

    write_slide, pending_slides, _written = _make_write_tools(db, outline_id, section_id)
    full_tools = [
        write_slide,
        pending_slides,
        make_search_knowledge(db, user_id, conversation_id, rag_mode, kb_count),
        make_search_web(web_count),
        make_fetch_web(db, user_id, conversation_id, fetch_count, agent_id=agent_id),
    ]

    system_prompt = build_generator_system_prompt()
    user_prompt = await build_generator_user_prompt(
        db=db, outline_id=outline_id, section_id=section_id,
        query=query, knowledge_mode=knowledge_mode,
        user_id=user_id, conversation_id=conversation_id,
    )

    llm, agent_id = create_llm(conversation_id)
    mws, _ = build_middlewares(conversation_id, agent_id)
    push_agent(conversation_id, agent_id)
    agent = create_agent(
        model=llm, tools=full_tools,
        system_prompt=system_prompt,
        middleware=mws,
    )

    writer({"type": "outline_generator_start", "section": section_title})

    # ── first attempt ──
    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            config={"recursion_limit": 80},
        )
    except Exception:
        _log.warning("generator crashed section=%d — retrying", section_id)
        _log.debug("generator crash detail", exc_info=True)
        result = {"messages": [HumanMessage(content=user_prompt)]}

    total_slides = len(await db.get_slides_by_outline_id(outline_id))
    sec_slides = sum(1 for s in (await db.get_slides_by_outline_id(outline_id)) if s.section_id == section_id)
    _log.info("generator section=%d written=%d/%d kb=%d web=%d fetch=%d",
              section_id, len(_written), sec_slides, kb_count[0], web_count[0], fetch_count[0])

    if len(_written) < sec_slides:
        _log.warning("generator retry section=%d (%d/%d written)", section_id, len(_written), sec_slides)

        # Collect all tool results into one string
        tool_texts: list[str] = []
        for m in result.get("messages", []):
            if isinstance(m, ToolMessage) and m.content:
                name = getattr(m, "name", "tool")
                tool_texts.append(f"### [{name}]\n{str(m.content)}")
        gathered = "\n\n---\n\n".join(tool_texts) if tool_texts else "（无知识搜索结果）"

        retry_user = await build_generator_user_prompt(
            db=db, outline_id=outline_id, section_id=section_id,
            query=query, knowledge_mode=knowledge_mode,
            user_id=user_id, conversation_id=conversation_id,
        )
        pending = await pending_slides.ainvoke({})
        retry_content = (
            f"{retry_user}\n\n"
            f"## 已收集的知识\n{gathered}\n\n"
            f"## 当前进度\n{pending}\n\n"
            f"---\n"
            f"⚠️ 请逐个调用 write_slide 完成所有待写入的幻灯片。用 pending_slides 查看进度。"
        )

        # New agent: only write_slide + pending_slides
        retry_agent = create_agent(
            model=llm, tools=[write_slide, pending_slides],
            system_prompt=system_prompt,
            middleware=mws,
        )
        try:
            await retry_agent.ainvoke(
                {"messages": [SystemMessage(content=system_prompt), HumanMessage(content=retry_content)]},
                config={"recursion_limit": 30},
            )
            _log.info("generator retry done section=%d written=%d/%d", section_id, len(_written), sec_slides)
        except Exception:
            _log.warning("generator retry failed section=%d", section_id)
            _log.debug("generator retry detail", exc_info=True)

    if len(_written) < sec_slides:
        _log.error("generator section=%d only %d/%d written", section_id, len(_written), sec_slides)
        return f"错误: 章节'{section_title}'仅完成 {len(_written)}/{sec_slides} 页"

    writer({"type": "outline_generator_end", "section": section_title})
    return f"章节'{section_title}'填充完成 ({len(_written)}页)"
