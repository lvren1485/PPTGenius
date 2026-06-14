"""Perception tools — 7 read-only DB tools for the Master Agent.

All take ``db: Database`` and auto-inject conversation_id / outline_id via closure.
Each tool uses Google-style docstrings so the @tool decorator extracts per-argument
descriptions for the LLM.
"""

from __future__ import annotations

import json
from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database


def make_get_conversation_status(
    db: Database, conversation_id: int
) -> Callable:
    """Return a tool that reads the full conversation + outlines + presentation state."""

    async def _get_conversation_status() -> dict:
        """List all outlines, presentations, and knowledge files for the current conversation.

        Call this first in every turn to orient yourself. Returns the active outline,
        all available outlines with their presentation status, and knowledge files.
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None:
            return {"error": f"Conversation {conversation_id} not found"}

        outlines = []
        for o in await db.list_outlines_by_conversation(conversation_id):
            sections = await db.get_sections_by_outline_id(o.id)
            pres_list = await db.list_presentations_by_conversation(conversation_id)
            pres_for_outline = next(
                (p for p in pres_list if p.outline_id == o.id and p.status != "deleted"),
                None,
            )
            pres_info = None
            if pres_for_outline:
                pres_info = {
                    "id": pres_for_outline.id,
                    "status": pres_for_outline.status,
                    "slide_count": pres_for_outline.slide_count,
                    "style_id": pres_for_outline.style_id,
                    "file_path": pres_for_outline.file_path,
                }
            outlines.append({
                "id": o.id,
                "title": o.title,
                "version": f"{o.version_major}.{o.version_minor}.{o.version_patch}",
                "section_count": len(sections),
                "slide_count": o.slide_count,
                "status": o.status,
                "presentation": pres_info,
            })

        kf_list = await db.list_knowledge_files(
            user_id=conv.user_id, conversation_id=conversation_id,
        )
        knowledge_files = [
            {
                "id": kf.id, "filename": kf.filename, "type": kf.file_type,
                "source_type": kf.source_type, "chunk_count": kf.chunk_count,
                "summary": kf.summary_json, "has_full_summary": kf.summary_json is not None,
            }
            for kf in kf_list
        ]

        return {
            "conversation_id": conversation_id,
            "current_outline_id": conv.current_outline_id,
            "outlines": outlines,
            "knowledge_files": knowledge_files,
        }

    return tool(_get_conversation_status)


def make_switch_outline(db: Database, conversation_id: int) -> Callable:
    """Return a tool to switch the active outline for this conversation."""

    async def _switch_outline(outline_id: int | None = None) -> str:
        """Switch the active outline for this conversation.

        Args:
            outline_id: The outline to switch to. Pass null to deselect the current outline.
        """
        await db.set_conversation_outline(conversation_id, outline_id)
        if outline_id is None:
            return "已取消选中大纲"
        outline = await db.get_outline(outline_id)
        if outline is None:
            return f"大纲(id={outline_id})不存在"
        slides = await db.get_slides_by_outline_id(outline_id)
        return f"已切换到大纲:'{outline.title}'(id={outline_id}, {len(slides)} slides)"

    return tool(_switch_outline)


def make_get_outline(db: Database, conversation_id: int) -> Callable:
    """Return a tool to read the current outline structure."""

    async def _get_outline(outline_id: int | None = None) -> dict:
        """Get the full outline structure with section and slide summaries.

        If outline_id is not provided, uses the current outline from the conversation.
        Returns sections with their slides, each slide showing title, layout_type, status,
        and a content summary.

        Args:
            outline_id: Optional explicit outline id. Omit to use current_outline_id.
        """
        oid = outline_id
        if oid is None:
            conv = await db.get_conversation(conversation_id)
            if conv is None or conv.current_outline_id is None:
                return {"error": "No outline selected. Use switch_outline or write_outline_structure first."}
            oid = conv.current_outline_id

        outline = await db.get_outline(oid)
        if outline is None:
            return {"error": f"Outline {oid} not found"}

        sections = await db.get_sections_by_outline_id(oid)
        slides = await db.get_slides_by_outline_id(oid)

        sec_data = []
        for s in sections:
            sec_slides = [sl for sl in slides if sl.section_id == s.id]
            sec_data.append({
                "id": s.id, "section_index": s.section_index, "title": s.title,
                "slide_count": len(sec_slides),
                "slides": [
                    {
                        "slide_index": sl.slide_index, "id": sl.id, "title": sl.title,
                        "layout_type": sl.layout_type, "status": sl.status,
                        "has_chart": sl.has_chart,
                        "summary": _slide_summary(sl),
                    }
                    for sl in sorted(sec_slides, key=lambda x: x.slide_index)
                ],
            })

        return {
            "id": outline.id, "title": outline.title,
            "version": f"{outline.version_major}.{outline.version_minor}.{outline.version_patch}",
            "status": outline.status, "slide_count": outline.slide_count,
            "sections": sec_data,
        }

    return tool(_get_outline)


def make_get_outline_slide(db: Database, conversation_id: int) -> Callable:
    """Return a tool to read a single slide's full content."""

    async def _get_outline_slide(slide_id: int) -> dict:
        """Read a single slide's complete content, citations, and notes.

        Use this before modifying a slide to see its full content_json.

        Args:
            slide_id: The id of the outline_slide to inspect.
        """
        slide = await db.get_outline_slide(slide_id)
        if slide is None:
            return {"error": f"Slide {slide_id} not found"}
        return {
            "id": slide.id, "outline_id": slide.outline_id,
            "slide_index": slide.slide_index, "title": slide.title,
            "layout_type": slide.layout_type, "status": slide.status,
            "content_json": slide.content_json,
            "citations": slide.citations,
            "notes": slide.notes,
            "has_image": slide.has_image, "has_chart": slide.has_chart,
        }

    return tool(_get_outline_slide)


def make_get_presentation(db: Database, conversation_id: int) -> Callable:
    """Return a tool to read the presentation state for the current outline."""

    async def _get_presentation(presentation_id: int | None = None) -> dict:
        """Read the presentation state for the current outline.

        Shows element count and types per slide. Defaults to the presentation
        associated with the current outline.

        Args:
            presentation_id: Optional explicit presentation id. Omit for current.
        """
        pid = presentation_id
        if pid is None:
            conv = await db.get_conversation(conversation_id)
            if conv is None or conv.current_outline_id is None:
                return {"error": "No outline selected."}
            pres_list = await db.list_presentations_by_conversation(conversation_id)
            matches = [p for p in pres_list
                       if p.outline_id == conv.current_outline_id and p.status != "deleted"]
            if not matches:
                return {"error": "No presentation for current outline."}
            pid = matches[0].id

        pres = await db.get_presentation(pid)
        if pres is None:
            return {"error": f"Presentation {pid} not found"}

        pslides = await db.get_slides_by_presentation_id(pid)
        slides_data = []
        for ps in sorted(pslides, key=lambda x: x.slide_index):
            outputs = ps.agent_outputs or {}
            slides_data.append({
                "slide_index": ps.slide_index, "id": ps.id,
                "layout_name": ps.layout_name, "status": ps.status,
                "element_count": len(outputs.get("elements", [])),
                "element_types": list({e.get("type") for e in outputs.get("elements", [])}),
            })

        return {
            "id": pres.id, "outline_id": pres.outline_id,
            "style_id": pres.style_id, "status": pres.status,
            "slide_count": pres.slide_count,
            "file_path": pres.file_path,
            "slides": slides_data,
        }

    return tool(_get_presentation)


def make_get_knowledge_files(db: Database, conversation_id: int) -> Callable:
    """Return a tool to list knowledge files for this conversation."""

    async def _get_knowledge_files() -> list[dict]:
        """List all knowledge files for the current conversation.

        Shows filename, type, and chunk count for each file.
        To explore file contents for structure suggestions, use explore_knowledge.
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None:
            return []
        kf_list = await db.list_knowledge_files(
            user_id=conv.user_id, conversation_id=conversation_id,
        )
        return [
            {
                "id": kf.id, "filename": kf.filename, "type": kf.file_type,
                "source_type": kf.source_type, "chunk_count": kf.chunk_count,
                "web_url": kf.web_url,
                "summary": kf.summary_json,
                "has_full_summary": kf.summary_json is not None,
            }
            for kf in kf_list
        ]

    return tool(_get_knowledge_files)


def make_search_styles(db: Database, conversation_id: int) -> Callable:
    """Return a tool to search available visual styles by keyword."""

    async def _search_styles(query: str = "") -> list[dict]:
        """Search available visual styles by keyword matching name or label.

        Args:
            query: Search keyword. Pass empty string to list all active styles.
        """
        styles = await db.search_styles(query)
        return [
            {
                "id": s.id, "name": s.name, "label": s.label,
                "colors": s.colors_json, "density": s.style_density,
            }
            for s in styles
        ]

    return tool(_search_styles)


def _slide_summary(sl) -> str:
    """Compact summary of a slide for get_outline overview."""
    parts = []
    cj = sl.content_json
    if isinstance(cj, str):
        cj = json.loads(cj)
    if cj:
        main = cj.get("main_points", [])
        if main:
            parts.append(f"main:{'|'.join(main[:3])}")
        detail = cj.get("detailed_content", "")
        if detail:
            parts.append(f"~{len(detail)}chars")
    if sl.has_chart:
        parts.append("has_chart")
    if not parts:
        parts.append("empty")
    return ", ".join(parts)
