"""Outline content generator — fills content_json for existing slides only."""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.middleware import build_middlewares
from ..common.sse_context import get_sse_writer
from pptgenius.infrastructure.llm import create_llm
from .prompts import build_generator_system_prompt, build_generator_user_prompt
from .prompts import _STATUS_HINTS

_log = get_logger("pptgenius.agent.outline.generator")


async def _build_citation_knowledge(db: Database, section) -> str:
    citations = section.citations or {}
    file_ids = citations.get("file_ids", [])[:4]
    chunk_ids = citations.get("chunk_ids", [])

    if not file_ids and not chunk_ids:
        return "本 section 无引用来源。"

    chunks_by_file: dict[int, list] = {}
    for fid in file_ids:
        db_chunks = await db.list_chunks_by_file(fid)
        chunks_by_file[fid] = sorted(db_chunks, key=lambda c: c.chunk_index)

    labeled: list[str] = []
    for fid in file_ids:
        clist = chunks_by_file.get(fid, [])
        if not clist:
            continue
        n = len(clist)
        indices = set()
        for i in range(min(15, n)):
            indices.add(i)
        for i in range(max(0, n - 5), n):
            indices.add(i)
        for i in sorted(indices):
            c = clist[i]
            labeled.append(f"[chunk_id={c.id}, file_id={fid}]\n{c.chunk_text}")

    if chunk_ids:
        for cid in chunk_ids[:10]:
            c = await db.get_chunk_by_id(cid)
            if c:
                labeled.append(f"[chunk_id={c.id}, file_id={c.file_id}]\n{c.chunk_text}")

    if not labeled:
        return "本 section 无引用来源。"

    text = "\n\n---\n\n".join(labeled)
    return f"## 知识库引用内容 ({len(labeled)} chunks)\n每个 chunk 标注了 chunk_id 和 file_id，write_slide 时必须引用。\n\n{text[:50_000]}"


# ── write tools (single-slide) ──────────────────────────────────────────────────


def _make_write_tools(db: Database, outline_id: int, section_id: int):
    _written: set[int] = set()

    @tool
    async def write_slide(
        slide_index: int,
        title: str,
        content_json: str | dict,
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
        content_json : str | dict — {main_points: [...], detailed_content: "...", key_data: "...", visual_note: "...", recommended_ppt_format: "..."}. String or dict accepted.
        has_image : bool — whether the slide needs an image.
        has_chart : bool — whether the slide needs a chart.
        notes : str — speaker notes (optional).
        citations : list[dict] | None — [{chunk_id, reason}, ...] for knowledge sources used.
        """
        if isinstance(content_json, str):
            try:
                content_json = json.loads(content_json)
            except json.JSONDecodeError:
                return f"错误: content_json 不是合法的 JSON: {content_json[:100]}"
        if not isinstance(content_json, dict):
            return f"错误: content_json 必须是 dict 或 JSON 字符串，收到了 {type(content_json).__name__}"

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
            return "所有幻灯片已写入。请结束本次对话。"
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
    language: str = "简体中文",
) -> str:
    """Fill content for one section's pre-created slides."""
    writer = get_sse_writer()

    section = await db.get_outline_section(section_id)
    if section is None:
        return f"错误: section {section_id} 不存在"
    outline_id = section.outline_id
    section_title = section.title

    outline = await db.get_outline(outline_id)

    write_slide, pending_slides, _written = _make_write_tools(db, outline_id, section_id)
    # Generator no longer has search tools — knowledge comes from citations
    full_tools = [write_slide, pending_slides]

    # Build knowledge text from section citations
    knowledge_text = await _build_citation_knowledge(db, section)

    system_prompt = build_generator_system_prompt()
    user_prompt = await build_generator_user_prompt(
        db=db, outline_id=outline_id, section_id=section_id,
        query=query, knowledge_mode=knowledge_mode, language=language,
    )
    if knowledge_text:
        user_prompt = knowledge_text + "\n\n" + user_prompt

    llm, agent_id = create_llm(conversation_id)
    mws, _ = build_middlewares(conversation_id, agent_id)
    push_agent(conversation_id, agent_id)
    agent = create_agent(
        model=llm, tools=full_tools,
        system_prompt=system_prompt,
        middleware=mws,
    )

    writer({"type": "outline_generator_start", "section": section_title})

    sec_slides = sum(1 for s in (await db.get_slides_by_outline_id(outline_id)) if s.section_id == section_id)
    messages = [HumanMessage(content=user_prompt)]

    from pptgenius.infrastructure.config.settings import get_settings
    max_retries = get_settings().agent.outline.generator_max_retries
    result = None

    for attempt in range(max_retries + 1):
        crashed = False
        try:
            result = await agent.ainvoke(
                {"messages": messages},
                config={"recursion_limit": 80},
            )
        except Exception:
            _log.warning("generator crashed section=%d attempt=%d", section_id, attempt)
            _log.debug("generator crashed details", exc_info=True)
            crashed = True

        _log.info("generator section=%d attempt=%d written=%d/%d",
                  section_id, attempt, len(_written), sec_slides)

        if len(_written) >= sec_slides:
            break

        if attempt >= max_retries:
            break

        # Fresh conversation — never carry forward old history
        pending = await pending_slides.ainvoke({})
        retry_msg = (
            f"## 当前进度\n{pending}\n\n"
            f"请继续逐个调用 write_slide 完成剩余的幻灯片。"
        )
        messages = [HumanMessage(content=user_prompt), HumanMessage(content=retry_msg)]

    if len(_written) < sec_slides:
        _log.error("generator section=%d only %d/%d written after %d attempts",
                    section_id, len(_written), sec_slides, max_retries + 1)
        return f"错误: 章节'{section_title}'仅完成 {len(_written)}/{sec_slides} 页"

    writer({"type": "outline_generator_end", "section": section_title})
    return f"章节'{section_title}'填充完成 ({len(_written)}页)"
