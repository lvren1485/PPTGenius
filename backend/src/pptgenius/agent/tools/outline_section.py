"""Outline section tools — thin wrappers delegating to agent/outline/generator.py."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.tool_sse_wrapper import wrap_tool_with_sse
from ..outline.generator import run_outline_generator

_log = get_logger("pptgenius.agent.tools.outline_section")


def make_generate_outline_content(db: Database, conversation_id: int) -> Callable:
    """Batch tool: generate content for ALL sections concurrently."""

    async def _generate_outline_content(
        query: str | None = None,
    ) -> str:
        """Generate slide content for ALL sections at once.

        This is the MAIN generation entry point. Invokes the generator for
        every section and waits for all to complete.

        Args:
            query: Optional user requirements or additional instructions.
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None or conv.current_outline_id is None:
            return "错误：没有选中大纲，请先创建或切换大纲"

        outline_id = conv.current_outline_id
        sections = await db.get_sections_by_outline_id(outline_id)
        if not sections:
            return "错误：当前大纲没有章节"

        _log.info("batch generate start: outline=%d sections=%d", outline_id, len(sections))
        for sec in sections:
            await run_outline_generator(
                db, conversation_id,
                section_id=sec.id,
                query=query,
            )

        await db.update_outline_status(outline_id, "completed")
        return f"全部生成完成: {len(sections)} 章节"

    return tool(wrap_tool_with_sse(_generate_outline_content))


def make_modify_outline_section(db: Database, conversation_id: int) -> Callable:
    """Single tool: modify/re-generate one section."""

    async def _modify_outline_section(
        section_id: int,
        query: str | None = None,
    ) -> str:
        """Regenerate content for flagged slides in a section.

        Use ONLY for modifying existing content. Before calling, mark slides
        needing changes via modify_outline_structure (rename with flag suffixes
        like "待修改").

        Args:
            section_id: The section to regenerate.
            query: Optional specific requirements or instructions.
        """
        _log.info("modify section: section_id=%d query=%s", section_id, query or "-")
        return await run_outline_generator(
            db, conversation_id,
            section_id=section_id,
            query=query,
        )

    return tool(wrap_tool_with_sse(_modify_outline_section))
