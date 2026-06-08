"""Outline sub-agent prompts — loads system prompts from resources/prompts/outline/."""

from __future__ import annotations

from functools import lru_cache

from pptgenius.infrastructure.config.settings import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database

_PROMPT_DIR = RESOURCES_DIR / "prompts" / "outline"


@lru_cache(maxsize=1)
def _load_generator_system() -> str:
    return (_PROMPT_DIR / "generator_system.txt").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_evaluator_system() -> str:
    return (_PROMPT_DIR / "evaluator_system.txt").read_text(encoding="utf-8")


def build_generator_system_prompt() -> str:
    return _load_generator_system()


_FLAGS = ("待合并", "待分割", "待填充", "新页", "待修改")


async def build_generator_user_prompt(
    *,
    db: Database,
    outline_id: int,
    section_id: int,
    query: str | None = None,
    knowledge_mode: str = "auto",
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
            flag = _detect_flag(sl)
            parts.append(_format_slide(sl, flag))

    # 3. Query
    if query:
        parts.append(f"## 用户说明\n{query}\n")

    # 4. Flagged slides notice
    flagged = [sl for sl in all_slides
               if sl.section_id == section_id and _detect_flag(sl)]
    if flagged:
        ids = [str(sl.slide_index) for sl in flagged]
        parts.append(f"**待处理**: slide {', '.join(ids)} 标记为空白或待修改，优先填充。\n")
    parts.append("幻灯片已预先创建且不可增删。使用 write_slides 按 slide_index 写入 content_json。")

    return "\n".join(parts)


def _detect_flag(slide) -> str | None:
    if not slide.content_json or not slide.content_json.get("main_points"):
        return "空白"
    title = slide.title or ""
    for flag in _FLAGS:
        if flag in title:
            return flag
    return None


def _format_slide(sl, flag: str | None) -> str:
    tag = f" [{flag}]" if flag else ""
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


def load_rubric() -> dict:
    import json
    return json.loads((_PROMPT_DIR / "rubric.json").read_text(encoding="utf-8"))


def format_rubric_for_prompt() -> str:
    r = load_rubric()
    lines = [f"## {r['name']}（满分 {r['total_max']} 分）", ""]
    for dim in r["dimensions"]:
        lines.append(f"### {dim['label']} ({dim['key']}) — 满分 {dim['max_score']} 分")
        lines.append(f"{dim['description']}")
        lines.append("")
        for score, desc in sorted(dim["criteria"].items(), key=lambda x: -int(x[0])):
            lines.append(f"- **{score}分**：{desc}")
        lines.append("")
    lines.append(f"**总分计算公式**：`{r['total_formula']}`")
    return "\n".join(lines)


def compute_outline_metrics(slides: list) -> dict:
    lt_counts: dict[str, int] = {}
    fmt_counts: dict[str, int] = {}
    img_count = 0
    chart_count = 0
    content_page_count = 0
    content_total_len = 0
    formats_in_order: list[str] = []

    for s in slides:
        lt = s.layout_type if hasattr(s, 'layout_type') else s.get('layout_type', 'content')
        lt_counts[lt] = lt_counts.get(lt, 0) + 1

        cj = s.content_json if hasattr(s, 'content_json') else s.get('content_json', {})
        if isinstance(cj, dict):
            fmt = cj.get('recommended_ppt_format', 'unknown')
            if cj.get('detailed_content'):
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
        "content_richness_score": _slide_count_score(total) + _content_len_score(avg),
        "layout_type_counts": lt_counts,
        "layout_type_variety": len(lt_counts),
        "format_counts": fmt_counts,
        "format_variety": len(fmt_counts),
        "max_consecutive_same_format": max_consecutive,
        "image_ratio": f"{img_count}/{total}",
        "chart_ratio": f"{chart_count}/{total}",
    }


def _slide_count_score(total: int) -> float:
    if 16 <= total <= 24: return 5.0
    if 12 <= total <= 15: return 4.0
    if 8 <= total <= 11: return 3.0
    if 5 <= total <= 7: return 2.0
    if 25 <= total <= 28: return 3.5
    return 1.0 if total < 5 else 2.0


def _content_len_score(avg_len: int) -> float:
    if avg_len >= 400: return 5.0
    if avg_len >= 300: return 4.0
    if avg_len >= 200: return 3.0
    if avg_len >= 100: return 2.0
    return 1.0


def format_metrics_for_prompt(metrics: dict) -> str:
    lines = [
        f"- 总页数: {metrics['total_slides']}（content 页: {metrics['content_page_count']}，理想范围 12-24）",
        f"- content 页平均 detailed_content 长度: {metrics['avg_content_length']} 字符（理想 >= 400）",
        f"- 内容丰富度参考分: {metrics['content_richness_score']}/10（机械计算，仅供参考）",
        f"- layout_type 分布: {metrics['layout_type_counts']}（共 {metrics['layout_type_variety']} 种）",
        f"- recommended_ppt_format 分布: {metrics['format_counts']}（共 {metrics['format_variety']} 种）",
        f"- 同一 format 最大连续使用: {metrics['max_consecutive_same_format']} 页",
        f"- 含图片页面: {metrics['image_ratio']}, 含图表页面: {metrics['chart_ratio']}",
    ]
    return "\n".join(lines)
