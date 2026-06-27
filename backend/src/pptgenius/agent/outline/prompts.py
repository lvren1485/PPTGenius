"""Outline sub-agent prompts — loads system prompts from resources/prompts/outline/."""

from __future__ import annotations

from functools import lru_cache

from pptgenius.infrastructure.config.settings import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database

_PROMPT_DIR = RESOURCES_DIR / "prompts" / "outline"


@lru_cache(maxsize=1)
def _load_generator_system() -> str:
    return (_PROMPT_DIR / "generator_system.md").read_text(encoding="utf-8")


def build_generator_system_prompt() -> str:
    return _load_generator_system()


async def build_generator_user_prompt(
    *,
    db: Database,
    outline_id: int,
    section_id: int,
    query: str | None = None,
    knowledge_mode: str = "auto",
    user_id: int = 0,
    conversation_id: int = 0,
    language: str = "简体中文",
) -> str:
    """Build the generator user prompt: all-section summaries + current section full."""

    sections = await db.get_sections_by_outline_id(outline_id)
    all_slides = await db.get_slides_by_outline_id(outline_id)

    current_section = None
    for s in sections:
        if s.id == section_id:
            current_section = s
            break

    parts = []

    # 0. Knowledge files (if any)
    if user_id and conversation_id:
        kf_list = await db.list_knowledge_files(user_id, conversation_id=conversation_id)
        if kf_list:
            parts.append("## 可用知识文件")
            parts.append("以下文件已上传到知识库，内容已在 prompt 开头的知识库引用内容中提供。使用 write_slide 时从中引用 citations。")
            for kf in kf_list:
                parts.append(f"  - file_id={kf.id}: {kf.filename} ({kf.chunk_count or '?'} chunks)")
            parts.append("")

    # 1. All sections brief
    parts.append("## 大纲概览")
    for s in sections:
        sec_slides = sorted(
            [sl for sl in all_slides if sl.section_id == s.id],
            key=lambda x: x.slide_index,
        )
        marker = " ← 当前" if s.id == section_id else ""
        parts.append(f"- {s.title} ({len(sec_slides)}页){marker}")
    parts.append("")

    # 2. Current section full slides
    if current_section:
        parts.append(f"## 当前章节: {current_section.title}")
        if current_section.description:
            parts.append(f"描述: {current_section.description}")
        parts.append("")

        sec_slides = sorted(
            [sl for sl in all_slides if sl.section_id == current_section.id],
            key=lambda x: x.slide_index,
        )
        for sl in sec_slides:
            parts.append(_format_slide(sl))

    # 3. Language
    parts.append(f"## 输出语言\n必须使用 **{language}** 撰写所有内容。")

    # 4. Query
    if query:
        parts.append(f"## 用户说明\n{query}\n")

    # 4. Flagged slides notice — show specific action per status
    flagged = [sl for sl in all_slides
               if sl.section_id == section_id and _needs_fill(sl)]
    if flagged:
        items = []
        for sl in flagged:
            hint = _status_hint(sl.status)
            items.append(f"  - slide_index={sl.slide_index}: {sl.title} [{sl.status}] — {hint}")
        parts.append("**待处理**:")
        parts.extend(items)
        parts.append("")
    parts.append("幻灯片已预先创建且不可增删。使用 write_slide 按 slide_index 写入 content_json。")
    parts.append("**每页 slide 的 title 字段必须填写**——提供干净、具体的标题。")

    return "\n".join(parts)


_STATUS_HINTS = {
    "new":    "新创建的空白页面，需要从零填充完整内容",
    "merge":  "内容来自被删除页面合并，需要重新组织融合后的内容",
    "split":  "内容从原页面复制，需要调整为独立页面",
    "modify": "用户要求修改的页面，按要求调整内容",
}


def _needs_fill(slide) -> bool:
    """Check if slide needs content generation — status is not 'completed'."""
    return slide.status != "completed"


def _status_hint(status: str | None) -> str:
    if not status:
        return "空白页，需要填充完整内容"
    return _STATUS_HINTS.get(status, f"状态异常 ({status})，需要填充内容")


def _format_slide(sl) -> str:
    tag = f" [{sl.status}]" if sl.status and sl.status != "completed" else ""
    content = sl.content_json or {}
    mp = content.get("main_points", [])
    dc = content.get("detailed_content", "")

    lines = [f"### slide_index={sl.slide_index}: {sl.title} ({sl.layout_type}){tag}"]
    if mp:
        lines.append(f"main_points: {'; '.join(mp[:5])}")
    if dc:
        preview = dc[:200] + "..." if len(dc) > 200 else dc
        lines.append(f"detailed: {preview}")
    if not mp and not dc:
        lines.append("(空白)")
    return "\n".join(lines) + "\n"


