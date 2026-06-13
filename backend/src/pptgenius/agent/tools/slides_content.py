"""slides_content tool — parallel slide generation with asyncio.gather.

Each slide agent runs purely in memory (zero DB access during ReAct).
Results are collected and written to DB serially in the main session.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.config import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_sentinel
from ..common.tool_sse_wrapper import wrap_tool_with_sse
from ..ppt.slide_agent import run_slide_agent

_log = get_logger("pptgenius.agent.tools.slides_content")

_LAYOUTS_DIR = RESOURCES_DIR / "layouts"


def _load_layout(name: str) -> dict | None:
    """Load a single layout JSON by name.  Returns None if not found."""
    path = _LAYOUTS_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _load_all_layouts() -> dict[str, dict]:
    """Load all layout JSONs.  Returns {name: dict}."""
    layouts = {}
    for f in sorted(_LAYOUTS_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            layouts[d.get("name", f.stem)] = d
        except Exception:
            pass
    return layouts


def _resolve_citations(citations, known_files: dict[int, dict]) -> str:
    """Turn citations [{knowledge_file_id: N}] into reference text."""
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


async def _resolve_slide_data(
    db: Database,
    slide,
    known_files: dict[int, dict],
) -> dict:
    """Build the slide dict expected by run_slide_agent."""
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


def make_slides_content(db: Database, conversation_id: int) -> Callable:

    async def _slides_content(
        query: str | None = None,
        slides: list[dict] | None = None,
        modify_instructions: dict | None = None,
    ) -> str:
        """Generate visual content for all presentation slides in parallel.

        Call after ppt_style has selected a style. Each slide is generated
        independently and concurrently.

        Args:
            query: Optional user requirements, e.g. "全部背景改为深色".
            slides: Optional list of slide overrides. Omit to generate all slides.
            modify_instructions: Per-slide modify instructions, e.g. {5: "饼图→柱状图"}.
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None or conv.current_outline_id is None:
            return "错误：没有选中大纲"

        outline_id = conv.current_outline_id

        # Find presentation
        pres_list = await db.list_presentations_by_conversation(conversation_id)
        pres = next(
            (p for p in pres_list if p.outline_id == outline_id and p.status != "deleted"),
            None,
        )
        if pres is None:
            return "错误：没有关联的 presentation。请先调用 ppt_style。"

        # Load style
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

        # Load all layouts as reference
        all_layouts = _load_all_layouts()

        # Load outline slides
        outline_slides = await db.get_slides_by_outline_id(outline_id)
        if not outline_slides:
            return "错误：大纲没有 slide。"

        # Resolve known files for citations
        kf_list = await db.list_knowledge_files(
            user_id=conv.user_id, conversation_id=conversation_id,
        )
        known_files = {kf.id: {"filename": kf.filename, "web_url": kf.web_url}
                       for kf in kf_list}

        # Prepare slide data for each outline slide
        slide_data_list = [
            await _resolve_slide_data(db, sl, known_files)
            for sl in sorted(outline_slides, key=lambda x: x.slide_index)
        ]

        _log.info("slides_content: generating %d slides in parallel", len(slide_data_list))
        push_sentinel(conversation_id)

        # ── parallel generation (pure memory, no DB) ──
        async def _gen_one(sd: dict) -> dict:
            layout = all_layouts.get(sd["layout_type"])
            per_slide_query = None
            if modify_instructions and sd["id"] in modify_instructions:
                per_slide_query = modify_instructions[sd["id"]]
            elif query:
                per_slide_query = query

            return await run_slide_agent(
                conversation_id=conversation_id,
                slide=sd,
                style=style_data,
                template=layout,
                query=per_slide_query,
            )

        results = await asyncio.gather(*[_gen_one(sd) for sd in slide_data_list])

        # ── serial DB write ──
        # Ensure presentation_slides exist (idempotent — create if missing)
        existing_pslides = await db.get_slides_by_presentation_id(pres.id)
        existing_by_index = {ps.slide_index: ps for ps in existing_pslides}

        for sd in slide_data_list:
            idx = sd["slide_index"]
            if idx not in existing_by_index:
                await db.create_presentation_slide(
                    presentation_id=pres.id,
                    slide_index=idx,
                    layout_name=sd["layout_type"],
                    outline_slide_id=sd["id"],
                    style_id=pres.style_id,
                )

        for r in results:
            si = r["slide_index"]
            outline_slide = next((sl for sl in outline_slides if sl.slide_index == si), None)

            # Assemble notes: outline notes → citations → visual notes
            outline_notes = (outline_slide.notes or "") if outline_slide else ""
            citations_text = _resolve_citations(
                (outline_slide.citations or []) if outline_slide else [],
                known_files,
            )
            visual_notes = r.get("notes", "")

            notes_parts = [p for p in [outline_notes, citations_text, visual_notes] if p]
            final_notes = "\n\n".join(notes_parts)

            agent_outputs = {
                "background": r.get("background", {}),
                "elements": r.get("elements", []),
                "notes": final_notes,
            }
            await db.set_slide_agent_output(
                presentation_id=pres.id,
                slide_index=si,
                agent_outputs=agent_outputs,
            )

        await db.update_presentation_status(pres.id, "slides_completed")
        await db.set_presentation_output(
            pres.id, file_path="", file_size=0, slide_count=len(results),
        )

        failed = sum(1 for r in results if not r.get("elements") and not r.get("background"))
        return f"{len(results) - failed}/{len(results)} 完成" + (f", {failed} 失败" if failed else "")

    return tool(wrap_tool_with_sse(_slides_content))
