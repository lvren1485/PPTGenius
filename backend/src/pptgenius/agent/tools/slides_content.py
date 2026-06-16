"""slides_content tool — parallel slide generation with asyncio.gather.

Each slide agent runs purely in memory (zero DB access during ReAct).
Results are collected and written to DB serially in the main session.

Exports:
  make_slides_content  — generate ALL slides from the active outline
  make_modify_slides_content — modify specific slides by outline_slide_id
  Both call _write_slide_content internally.
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.config import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_sentinel
from ..ppt.slide_agent import run_slide_agent

_log = get_logger("pptgenius.agent.tools.slides_content")

_LAYOUTS_DIR = RESOURCES_DIR / "layouts"


# ── helpers ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_template_catalog() -> dict[str, dict]:
    """Load the 3 comprehensive template files (title / section / content)."""
    templates = {}
    for fname in ("template_title.json", "template_section.json", "template_content.json"):
        path = _LAYOUTS_DIR / fname
        if path.exists():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                templates[d.get("type", fname)] = d
            except Exception:
                pass
    return templates


_LAYOUT_TYPE_MAP: dict[str, str] = {
    "title": "title", "title_slide": "title",
    "thanks": "title", "ending": "title",
    "section": "section",
    "content": "content",
}


def _resolve_citations(citations, known_files: dict[int, dict]) -> str:
    if not citations:
        return ""
    lines = ["参考来源:"]
    for i, c in enumerate(citations, 1):
        fid = c.get("knowledge_file_id") if isinstance(c, dict) else c
        info = known_files.get(fid, {})
        filename = info.get("filename", f"文件#{fid}")
        web_url = info.get("web_url", "")
        if web_url:
            lines.append(f"[{i}] {filename} ({web_url})")
        else:
            lines.append(f"[{i}] {filename}")
    return "\n".join(lines)


def _resolve_slide_data(slide) -> dict:
    content_json = slide.content_json or {}
    if isinstance(content_json, str):
        try:
            content_json = json.loads(content_json)
        except json.JSONDecodeError:
            content_json = {}

    return {
        "slide_index": slide.slide_index,
        "id": slide.id,
        "title": slide.title or "",
        "layout_type": slide.layout_type or "content",
        "content_json": content_json,
        "has_chart": slide.has_chart or False,
        "has_image": slide.has_image or False,
        "notes": slide.notes or "",
        "citations": slide.citations or [],
    }


async def _load_context(
    db: Database, conversation_id: int
) -> tuple[dict | None, dict[str, dict], dict[int, dict], object, int, int]:
    """Return (style_data, templates, known_files, conv, outline_id, pres_id)."""
    conv = await db.get_conversation(conversation_id)
    if conv is None or conv.current_outline_id is None:
        return None, {}, {}, conv, 0, 0

    outline_id = conv.current_outline_id
    pres_list = await db.list_presentations_by_conversation(conversation_id)
    pres = next(
        (p for p in pres_list if p.outline_id == outline_id and p.status != "deleted"),
        None,
    )
    if pres is None:
        return None, {}, {}, conv, outline_id, 0

    style_data = None
    if pres.style_id:
        s = await db.get_style(pres.style_id)
        if s:
            style_data = {
                "id": s.id, "name": s.name, "label": s.label,
                "colors": s.colors_json,
                "chart_colors": s.chart_colors_json,
                "fonts": s.fonts_json,
                "style_density": s.style_density,
                "background_json": s.background_json,
            }

    templates = _load_template_catalog()
    kf_list = await db.list_knowledge_files(
        user_id=conv.user_id, conversation_id=conversation_id,
    )
    known_files = {kf.id: {"filename": kf.filename, "web_url": kf.web_url}
                   for kf in kf_list}

    return style_data, templates, known_files, conv, outline_id, pres.id


# ── intermediate: generate + write one slide ─────────────────────────────

async def _write_slide_content(
    db: Database,
    conversation_id: int,
    outline_slide,
    style_data: dict | None,
    templates: dict[str, dict],
    known_files: dict[int, dict],
    query: str | None,
    pres_id: int,
) -> dict:
    """Generate and persist ONE slide.  Returns the agent result dict."""

    sd = _resolve_slide_data(outline_slide)

    # Read existing agent outputs (for modify mode awareness)
    existing = await db.get_slides_by_presentation_id(pres_id)
    existing_ps = next((ps for ps in existing if ps.slide_index == sd["slide_index"]), None)
    existing_outputs = existing_ps.agent_outputs if existing_ps and existing_ps.agent_outputs else None

    # Map layout_type to template category, pass all 3 templates as catalog
    template_type = _LAYOUT_TYPE_MAP.get(sd["layout_type"], "content")
    matched_template = templates.get(template_type)

    # Generate (pure memory)
    result = await run_slide_agent(
        conversation_id=conversation_id,
        slide=sd,
        style=style_data,
        template=matched_template,
        query=query,
        existing_outputs=existing_outputs,
    )

    # Ensure presentation_slide row exists
    existing = await db.get_slides_by_presentation_id(pres_id)
    existing_by_idx = {ps.slide_index: ps for ps in existing}
    idx = sd["slide_index"]
    if idx not in existing_by_idx:
        await db.create_presentation_slide(
            presentation_id=pres_id,
            slide_index=idx,
            layout_name=sd["layout_type"],
            outline_slide_id=sd["id"],
            style_id=style_data["id"] if style_data else None,
        )

    # Assemble notes
    outline_notes = outline_slide.notes or ""
    citations_text = _resolve_citations(outline_slide.citations or [], known_files)
    visual_notes = result.get("notes", "")
    notes_parts = [p for p in [outline_notes, citations_text, visual_notes] if p]
    final_notes = "\n\n".join(notes_parts)

    agent_outputs = {
        "background": result.get("background", {}),
        "elements": result.get("elements", []),
        "notes": final_notes,
    }
    await db.set_slide_agent_output(
        presentation_id=pres_id,
        slide_index=idx,
        agent_outputs=agent_outputs,
    )

    _log.debug("slide %d written: %d elements, bg=%s",
               idx, len(result.get("elements", [])),
               result.get("background", {}).get("type", "none"))
    return result


# ── tool: generate ALL slides ────────────────────────────────────────────

def make_slides_content(db: Database, conversation_id: int) -> Callable:

    async def _slides_content(
        query: str | None = None,
        modify_instructions: dict | None = None,
    ) -> str:
        """Generate visual content for ALL slides of the active outline.

        Runs all slides in parallel, then writes results to DB serially.

        Args:
            query: Optional user requirements, e.g. "全部背景改为深色".
            modify_instructions: Per-slide modify instructions by slide ID, e.g. {5: "饼图→柱状图"}.
        """
        style_data, templates, known_files, conv, outline_id, pres_id = \
            await _load_context(db, conversation_id)

        if pres_id == 0:
            return "错误：没有关联的 presentation。请先调用 ppt_style。"
        if outline_id == 0:
            return "错误：没有选中大纲"

        outline_slides = sorted(
            await db.get_slides_by_outline_id(outline_id),
            key=lambda x: x.slide_index,
        )
        if not outline_slides:
            return "错误：大纲没有 slide。"

        _log.info("slides_content: generating %d slides", len(outline_slides))
        push_sentinel(conversation_id)

        results = await asyncio.gather(*[
            _write_slide_content(
                db, conversation_id,
                outline_slide=sl,
                style_data=style_data,
                templates=templates,
                known_files=known_files,
                query=(
                    modify_instructions.get(sl.id)
                    if modify_instructions and sl.id in modify_instructions
                    else query
                ),
                pres_id=pres_id,
            )
            for sl in outline_slides
        ])

        await db.update_presentation_status(pres_id, "completed")
        await db.set_presentation_output(
            pres_id, file_path="", file_size=0, slide_count=len(results),
        )

        failed = sum(1 for r in results if not r.get("elements") and not r.get("background"))
        return f"{len(results) - failed}/{len(results)} 完成" + (f", {failed} 失败" if failed else "")

    return tool(_slides_content)


# ── tool: modify specific slides ─────────────────────────────────────────

def make_modify_slides_content(db: Database, conversation_id: int) -> Callable:

    async def _modify_slides_content(
        slide_ids: list[int],
        query: str | None = None,
        modify_instructions: dict | None = None,
    ) -> str:
        """Modify specific slides in the active presentation.

        Args:
            slide_ids: List of outline_slide IDs to regenerate.
            query: Optional overall modification requirements.
            modify_instructions: Per-slide modify instructions by slide ID, e.g. {5: "柱状图→饼图"}.
        """
        style_data, templates, known_files, conv, outline_id, pres_id = \
            await _load_context(db, conversation_id)

        if pres_id == 0:
            return "错误：没有关联的 presentation。请先调用 ppt_style。"

        all_slides = await db.get_slides_by_outline_id(outline_id)
        targets = [sl for sl in all_slides if sl.id in slide_ids]
        if not targets:
            return f"错误：未找到指定的 slide ID: {slide_ids}"

        _log.info("modify_slides_content: regenerating %d slides", len(targets))
        push_sentinel(conversation_id)

        results = await asyncio.gather(*[
            _write_slide_content(
                db, conversation_id,
                outline_slide=sl,
                style_data=style_data,
                templates=templates,
                known_files=known_files,
                query=(
                    modify_instructions.get(sl.id)
                    if modify_instructions and sl.id in modify_instructions
                    else query
                ),
                pres_id=pres_id,
            )
            for sl in targets
        ])

        failed = sum(1 for r in results if not r.get("elements") and not r.get("background"))
        return f"已修改 {len(results) - failed}/{len(results)} 页" + (f", {failed} 失败" if failed else "")

    return tool(_modify_slides_content)
