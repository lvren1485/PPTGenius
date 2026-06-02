"""Prompt loading and formatting for outline generator / evaluator."""

from __future__ import annotations

import json
from pathlib import Path

from pptgenius.infrastructure.config import RESOURCES_DIR

_PROMPT_DIR = RESOURCES_DIR / "prompts" / "outline"


def _load_text(filename: str) -> str:
    path = _PROMPT_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _load_json(filename: str) -> dict:
    path = _PROMPT_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Resource file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_generator_system() -> str:
    """Return the generator system prompt template."""
    return _load_text("generator_system.txt")


def load_evaluator_system() -> str:
    """Return the evaluator system prompt template."""
    return _load_text("evaluator_system.txt")


def load_rubric() -> dict:
    """Return the scoring rubric as a dict."""
    return _load_json("rubric.json")


def format_rubric_for_prompt() -> str:
    """Format the rubric as a human-readable string for inclusion in prompts."""
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


def build_generator_user_prompt(
    query: str,
    design_rationale: str = "",
    eval_suggestions: str = "",
    is_revision: bool = False,
) -> str:
    """Build the user prompt for the generator node.

    Parameters
    ----------
    query : str
        The user's original request or the evaluator's suggestions (revision).
    design_rationale : str
        Previous outline's design rationale (only for revision).
    eval_suggestions : str
        Evaluator's improvement suggestions (only for revision).
    is_revision : bool
        Whether this is a revision round.
    """
    if not is_revision:
        return f"请根据以下需求生成一份完整的PPT大纲：\n\n{query}"

    parts = ["请根据以下改进建议修改大纲：", "", eval_suggestions]
    if design_rationale:
        parts.extend(["", "## 上一版大纲的设计思路", "", design_rationale])
    parts.extend([
        "",
        "## 修改指引",
        "1. 你可以选择修改其中几页，也可以重新生成整个大纲",
        "2. 如果只修改部分页面，确保页面之间的逻辑仍然连贯",
        "3. 使用 write_outline 工具保存修改后的大纲",
    ])
    return "\n".join(parts)


def compute_outline_metrics(slides: list) -> dict:
    """Compute quantitative metrics from outline slides for evaluator."""
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
                # Only count content-type pages for avg
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
        elif isinstance(s, dict):
            if s.get('has_image'): img_count += 1
            if s.get('has_chart'): chart_count += 1

    # Max consecutive same format
    max_consecutive = 0
    current_consecutive = 1
    for i in range(1, len(formats_in_order)):
        if formats_in_order[i] == formats_in_order[i-1]:
            current_consecutive += 1
        else:
            max_consecutive = max(max_consecutive, current_consecutive)
            current_consecutive = 1
    max_consecutive = max(max_consecutive, current_consecutive)

    total = len(slides)
    avg_content_len = content_total_len // max(content_page_count, 1)
    return {
        "total_slides": total,
        "content_page_count": content_page_count,
        "avg_content_length": avg_content_len,
        "content_richness_score": _slide_count_score(total) + _content_len_score(avg_content_len),
        "layout_type_counts": lt_counts,
        "layout_type_variety": len(lt_counts),
        "format_counts": fmt_counts,
        "format_variety": len(fmt_counts),
        "max_consecutive_same_format": max_consecutive,
        "image_ratio": f"{img_count}/{total}",
        "chart_ratio": f"{chart_count}/{total}",
    }


def _slide_count_score(total: int) -> float:
    """Score slide count: 12-24 = ideal (5.0), below/above → lower."""
    if 16 <= total <= 24:
        return 5.0
    if 12 <= total <= 15:
        return 4.0
    if 8 <= total <= 11:
        return 3.0
    if 5 <= total <= 7:
        return 2.0
    if 25 <= total <= 28:
        return 3.5
    if total < 5:
        return 1.0
    return 2.0


def _content_len_score(avg_len: int) -> float:
    """Score content page avg description length: 400+ = ideal (5.0), below = lower."""
    if avg_len >= 400:
        return 5.0
    if avg_len >= 300:
        return 4.0
    if avg_len >= 200:
        return 3.0
    if avg_len >= 100:
        return 2.0
    return 1.0


def format_metrics_for_prompt(metrics: dict) -> str:
    """Format computed metrics as a readable string for the evaluator prompt."""
    lines = [
        f"- 总页数: {metrics['total_slides']}（content 页: {metrics['content_page_count']}，理想范围 12-24）",
        f"- content 页平均 detailed_content 长度: {metrics['avg_content_length']} 字符（理想 >= 400）",
        f"- 内容丰富度参考分: {metrics['content_richness_score']}/10（基于页数+内容长度，机械计算仅供参考）",
        f"- layout_type 分布: {metrics['layout_type_counts']}（共 {metrics['layout_type_variety']} 种）",
        f"- recommended_ppt_format 分布: {metrics['format_counts']}（共 {metrics['format_variety']} 种）",
        f"- 同一 format 最大连续使用: {metrics['max_consecutive_same_format']} 页",
        f"- 含图片页面: {metrics['image_ratio']}, 含图表页面: {metrics['chart_ratio']}",
    ]
    return "\n".join(lines)


def build_evaluator_user_prompt(
    outline_title: str,
    slides_text: str,
    design_rationale: str = "",
    metrics: dict | None = None,
    user_query: str = "",
) -> str:
    """Build the user prompt for the evaluator node."""
    parts = [
        "请对以下PPT大纲进行评审打分。",
        "",
        f"## 大纲标题：{outline_title}",
    ]
    if user_query:
        parts.extend(["", "## 用户原始需求", "", user_query])
    if design_rationale:
        parts.extend(["", "## 设计思路", "", design_rationale])
    if metrics:
        parts.extend([
            "",
            "## 大纲量化指标（程序自动计算，供参考）",
            "",
            format_metrics_for_prompt(metrics),
        ])
    scoring_notes = [
        "",
        "---",
        "请严格对照评分标准对五个维度分别打分（含 content_richness），参考量化指标但不要机械套用。",
        "如果量化指标显示明显问题（如 content 页平均 detailed_content 低于400字、layout_type 只有2种），必须在对应维度扣分。",
        "**如果用户原始需求中指定了页数要求，则 content_richness 维度只看 content 页文本长度（400字线），忽略总页数指标。**",
        "**如果用户原始需求未指定页数，则 content_richness 维度同时看总页数（12-24为佳）和文本长度。**",
        "**必须使用 submit_evaluation 工具提交评分。**",
    ]
    parts.extend(scoring_notes)
    return "\n".join(parts)
