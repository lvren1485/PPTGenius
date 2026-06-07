"""Outline section tools — thin wrappers delegating to agent/outline/generator.py."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database

from ..common.tool_sse_wrapper import wrap_tool_with_sse
from ..outline.generator import run_outline_generator


def make_generate_outline_content(db: Database, conversation_id: int) -> Callable:
    """Batch tool: generate content for ALL sections then reindex globally."""

    async def _generate_outline_content(
        query: str | None = None,
        knowledge_mode: str = "auto",
    ) -> str:
        """Generate slide content for ALL sections of the current outline at once.

        This is the MAIN generation entry point. After write_outline_structure,
        call this to fill all sections with content. Slides are reindexed globally.

        Args:
            query: Optional user requirements for content generation.
            knowledge_mode: "auto" (default), "refresh", "reuse", or "extend".
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None or conv.current_outline_id is None:
            return "错误：没有选中大纲，请先创建或切换大纲"

        outline_id = conv.current_outline_id
        sections = await db.get_sections_by_outline_id(outline_id)
        if not sections:
            return "错误：当前大纲没有章节"

        for sec in sections:
            await run_outline_generator(
                db, conversation_id,
                section_id=sec.id,
                query=query,
                knowledge_mode=knowledge_mode,
            )

        # Reindex globally
        slides = await db.get_slides_by_outline_id(outline_id)
        title_slides = [s for s in slides if s.layout_type == "title"]
        ending_slides = [s for s in slides if s.layout_type == "thanks"]
        toc_slides = [s for s in slides
                      if s.layout_type == "content" and "目录" in (s.title or "")]
        body_slides = [s for s in slides
                       if s.layout_type not in ("title", "thanks")
                       and s not in toc_slides]

        next_idx = 1
        for s in title_slides:
            await db.update_outline_slide_index(s.id, next_idx); next_idx += 1
        for s in toc_slides:
            await db.update_outline_slide_index(s.id, next_idx); next_idx += 1
        for sec in sections:
            for s in body_slides:
                if s.section_id == sec.id:
                    await db.update_outline_slide_index(s.id, next_idx); next_idx += 1
        for s in ending_slides:
            await db.update_outline_slide_index(s.id, next_idx); next_idx += 1

        total = next_idx - 1
        await db.update_outline_status(outline_id, "completed")
        return f"全部生成完成: {len(sections)} 章节, 共 {total} 页"

    return tool(wrap_tool_with_sse(_generate_outline_content))


def make_modify_outline_section(db: Database, conversation_id: int) -> Callable:
    """Single tool: modify/re-generate one section."""

    async def _modify_outline_section(
        section_id: int,
        query: str | None = None,
        knowledge_mode: str = "refresh",
        regenerate_slides: list[int] | None = None,
    ) -> str:
        """Regenerate content for a specific section or individual slides.

        Use ONLY for modifying existing content. For initial generation use
        generate_outline_content.

        Args:
            section_id: The section to regenerate.
            query: Optional specific requirements.
            knowledge_mode: "refresh" (default), "auto", "reuse", "extend".
            regenerate_slides: Optional slide IDs to target. Omit for all.
        """
        return await run_outline_generator(
            db, conversation_id,
            section_id=section_id,
            query=query,
            knowledge_mode=knowledge_mode,
            regenerate_slides=regenerate_slides,
        )

    return tool(wrap_tool_with_sse(_modify_outline_section))
