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


def build_evaluator_user_prompt(
    outline_title: str,
    slides_text: str,
    design_rationale: str = "",
) -> str:
    """Build the user prompt for the evaluator node.

    Parameters
    ----------
    outline_title : str
        The outline title.
    slides_text : str
        Formatted text of all slides with their content.
    design_rationale : str
        The generator's design rationale for this outline.
    """
    parts = [
        "请对以下PPT大纲进行评审打分。",
        "",
        f"## 大纲标题：{outline_title}",
    ]
    if design_rationale:
        parts.extend(["", "## 设计思路", "", design_rationale])
    parts.extend([
        "",
        "## 大纲全文",
        "",
        slides_text,
        "",
        "---",
        "请严格对照评分标准对三个维度分别打分，并给出具体的改进建议。",
        "**必须使用 submit_evaluation 工具提交评分。**",
    ])
    return "\n".join(parts)
