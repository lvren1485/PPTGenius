"""Outline sub-agent prompts — loads system prompts from resources/prompts/outline/."""

from __future__ import annotations

from functools import lru_cache

from pptgenius.infrastructure.config.settings import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database

_PROMPT_DIR = RESOURCES_DIR / "prompts" / "outline"


@lru_cache(maxsize=1)
def _load_generator_system() -> str:
    return (_PROMPT_DIR / "generator_system.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_evaluator_system() -> str:
    return (_PROMPT_DIR / "evaluator_system.md").read_text(encoding="utf-8")


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

    # 3. Query
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


def build_evaluator_system_prompt() -> str:
    return _load_evaluator_system()


def build_evaluator_user_prompt(
    outline_title: str,
    sections_count: int,
    slides_count: int,
    query: str | None = None,
) -> str:
    parts = [
        f"请对以下大纲进行评测:",
        f"大纲标题: {outline_title}",
        f"章节数: {sections_count}",
        f"总页数: {slides_count}",
    ]
    if query:
        parts.append(f"用户特别要求: {query}")
    return "\n".join(parts)


def compute_outline_metrics(slides: list) -> dict:
    fmt_counts: dict[str, int] = {}
    img_count = 0
    chart_count = 0
    content_page_count = 0
    content_total_len = 0
    formats_in_order: list[str] = []

    for s in slides:
        cj = s.content_json if hasattr(s, 'content_json') else s.get('content_json', {})
        if isinstance(cj, dict):
            fmt = cj.get('recommended_ppt_format', 'unknown')
            if cj.get('detailed_content'):
                lt = s.layout_type if hasattr(s, 'layout_type') else s.get('layout_type', 'content')
                if lt == 'content':
                    content_page_count += 1
                    content_total_len += len(cj['detailed_content'])
        else:
            fmt = 'unknown'

        fmt_counts[fmt] = fmt_counts.get(fmt, 0) + 1
        formats_in_order.append(fmt)

        if hasattr(s, 'has_image'):
            if s.has_image: img_count += 1
            if s.has_chart: chart_count += 1

    max_consecutive = 0
    current = 1
    for i in range(1, len(formats_in_order)):
        if formats_in_order[i] == formats_in_order[i-1]:
            current += 1
        else:
            max_consecutive = max(max_consecutive, current)
            current = 1
    max_consecutive = max(max_consecutive, current)

    total = len(slides)
    avg = content_total_len // max(content_page_count, 1)
    return {
        "total_slides": total,
        "content_page_count": content_page_count,
        "avg_content_length": avg,
        "content_richness_score": _content_len_score(avg),
        "format_counts": fmt_counts,
        "format_variety": len(fmt_counts),
        "max_consecutive_same_format": max_consecutive,
        "image_ratio": f"{img_count}/{total}",
        "chart_ratio": f"{chart_count}/{total}",
    }


def _content_len_score(avg_len: int) -> float:
    if avg_len >= 300: return 10.0
    if avg_len >= 250: return 8.0
    if avg_len >= 200: return 6.0
    if avg_len >= 150: return 4.0
    return 2.0


def format_metrics_for_prompt(metrics: dict) -> str:
    lines = [
        f"- 总页数: {metrics['total_slides']}（content 页: {metrics['content_page_count']}）",
        f"- content 页平均 detailed_content 长度: {metrics['avg_content_length']} 字符（理想 >= 300）",
        f"- 内容长度参考分: {metrics['content_richness_score']}/10（机械计算，仅供参考）",
        f"- recommended_ppt_format 分布: {metrics['format_counts']}（共 {metrics['format_variety']} 种）",
        f"- 同一 format 最大连续使用: {metrics['max_consecutive_same_format']} 页",
        f"- 含图片页面: {metrics['image_ratio']}, 含图表页面: {metrics['chart_ratio']}",
    ]
    return "\n".join(lines)
