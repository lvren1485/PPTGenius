"""Outline sub-agent prompts — loads system prompts from resources/prompts/outline/."""

from __future__ import annotations

from functools import lru_cache

from pptgenius.infrastructure.config.settings import RESOURCES_DIR

_PROMPT_DIR = RESOURCES_DIR / "prompts" / "outline"


@lru_cache(maxsize=1)
def _load_generator_system() -> str:
    return (_PROMPT_DIR / "generator_system.txt").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_evaluator_system() -> str:
    return (_PROMPT_DIR / "evaluator_system.txt").read_text(encoding="utf-8")


def build_generator_system_prompt() -> str:
    return _load_generator_system()


def build_generator_user_prompt(
    section_title: str,
    section_description: str,
    query: str | None = None,
    slide_titles: list[str] | None = None,
    is_regenerate: bool = False,
) -> str:
    parts = [f"## 章节: {section_title}"]
    if section_description:
        parts.append(f"描述: {section_description}")
    if query:
        parts.append(f"用户要求: {query}")
    if slide_titles:
        parts.append(f"需生成的页面: {', '.join(slide_titles)}")
    if is_regenerate:
        parts.append("注意: 这是重新生成，请根据现有内容进行改进。")
    return "\n".join(parts)


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
