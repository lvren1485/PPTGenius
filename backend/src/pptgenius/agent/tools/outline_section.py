"""Outline section tools — thin wrappers delegating to agent/outline/generator.py."""

from __future__ import annotations

import asyncio
from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.db.engine import get_session_manager
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_sentinel
from ..common.tool_sse_wrapper import wrap_tool_with_sse
from ..outline.generator import run_outline_generator

_log = get_logger("pptgenius.agent.tools.outline_section")


async def _finalize_special_slides(db: Database, outline_id: int) -> None:
    """Write hierarchical markdown to title, TOC, and thanks slides."""
    sections = await db.get_sections_by_outline_id(outline_id)
    slides = await db.get_slides_by_outline_id(outline_id)
    outline = await db.get_outline(outline_id)

    # Build hierarchical markdown
    md_lines = [f"# {outline.title if outline else ''}", ""]
    for s in sorted(sections, key=lambda x: x.section_index):
        sec_slides = sorted(
            [sl for sl in slides if sl.section_id == s.id],
            key=lambda x: x.slide_index,
        )
        md_lines.append(f"## {s.section_index}. {s.title}")
        for sl in sec_slides:
            t = sl.title or "(无标题)"
            lt = sl.layout_type or "content"
            md_lines.append(f"  - [{lt}] {t}")
        md_lines.append("")
    full_md = "\n".join(md_lines)

    # Generate TOC: just the hierarchical list
    toc_lines = [f"# 目录", ""]
    for s in sorted(sections, key=lambda x: x.section_index):
        sec_slides = sorted(
            [sl for sl in slides if sl.section_id == s.id],
            key=lambda x: x.slide_index,
        )
        toc_lines.append(f"## {s.section_index}. {s.title}")
        for sl in sec_slides:
            t = sl.title or "(无标题)"
            toc_lines.append(f"  - {t}")
        toc_lines.append("")
    toc_md = "\n".join(toc_lines)

    # Write to special slides by layout_type
    for sl in slides:
        lt = sl.layout_type or ""
        if lt == "title":
            await db.update_outline_slide(sl.id,
                content_json={
                    "main_points": [outline.title if outline else ""],
                    "detailed_content": full_md,
                    "key_data": "",
                    "visual_note": "封面页 — 标题大字鲜明，副标题说明演讲主题，可加演讲者信息、时间地点等",
                    "recommended_ppt_format": "title_slide",
                },
                status="completed",
            )
        elif lt == "content" and sl.slide_index == 0:
            # TOC slide: slide_index=0, layout_type=content, title contains "目录"
            t = sl.title or ""
            if "目录" in t or "目錄" in t or "TOC" in t.upper():
                await db.update_outline_slide(sl.id,
                    content_json={
                        "main_points": [f"{len(sections)} 个章节, {len(slides)} 页"],
                        "detailed_content": toc_md,
                        "key_data": "",
                        "visual_note": "目录页 — 形状、列表展示章节，各个章节可以添加副标题或关键词说明内容，突出层级关系",
                        "recommended_ppt_format": "bullet_list",
                    },
                    status="completed",
                )
        elif lt == "thanks":
            await db.update_outline_slide(sl.id,
                content_json={
                    "main_points": ["感谢观看"],
                    "detailed_content": full_md,
                    "key_data": "",
                    "visual_note": "结尾页 — 简洁致谢，可加联系方式或二维码",
                    "recommended_ppt_format": "title_slide",
                },
                status="completed",
            )

    _log.debug("special slides finalized for outline=%d", outline_id)


def make_generate_outline_content(db: Database, conversation_id: int) -> Callable:
    """Batch tool: generate content for ALL sections concurrently."""

    async def _generate_outline_content(
        query: str | None = None,
    ) -> str:
        """Generate slide content for ALL sections at once.

        This is the MAIN generation entry point. Invokes the generator for
        every section concurrently — each with its own DB session.

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
        push_sentinel(conversation_id)

        # Each generator gets its own DB session for safe concurrent execution
        sm = get_session_manager()

        async def _run_one(sec):
            gdb = sm.new_session()
            try:
                return await run_outline_generator(
                    gdb, conversation_id, section_id=sec.id, query=query,
                )
            finally:
                await sm.close(gdb)

        await asyncio.gather(*[_run_one(sec) for sec in sections])

        # Write hierarchical markdown to title / TOC / thanks slides
        await _finalize_special_slides(db, outline_id)

        await db.update_outline_status(outline_id, "completed")
        await db.increase_outline_version(conv.current_outline_id)
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
        conv = await db.get_conversation(conversation_id)
        if conv is None or conv.current_outline_id is None:
            return "错误：没有选中大纲"

        await db.increase_outline_version(conv.current_outline_id, "minor")
        push_sentinel(conversation_id)
        return await run_outline_generator(
            db, conversation_id,
            section_id=section_id,
            query=query,
        )

    return tool(wrap_tool_with_sse(_modify_outline_section))
