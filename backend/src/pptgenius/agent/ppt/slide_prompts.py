"""Slide agent prompt builder — loads templates from resources/prompts/ppt/."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pptgenius.agent.ppt.common.instruction_loader import (
    get_full_instruction_context,
    get_how_to_read,
    get_instruction,
    list_chart_instructions,
)
from pptgenius.infrastructure.config import RESOURCES_DIR

_PROMPTS_DIR = RESOURCES_DIR / "prompts" / "ppt"
_MAX_ICON_INCH = 0.79

_Z_ORDER_TABLE = """
z_order 参照 (越小越底层):
  0=背景 10=背景图 20=大装饰 30=图片 40=图表 50=表格
  60=小装饰 70=正文 80=标题 90=页码
"""


@lru_cache(maxsize=8)
def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt template not found: {path}")


@lru_cache(maxsize=1)
def build_system_prompt() -> str:
    """Build the slide agent system prompt ~8k tokens."""
    instruction_ctx = get_full_instruction_context()
    template = _load_prompt("content_agent_system.md")

    return template.format(
        howto=get_how_to_read(),
        textbox_inst=_j(get_instruction("textbox.json")),
        table_inst=_j(get_instruction("table.json")),
        picture_inst=_j(get_instruction("picture.json")),
        shape_inst=_j(get_instruction("shape.json")),
        background_inst=_j(get_instruction("background.json")),
        chart_list="\n".join(
            f"- `{c['chart_type']}`: {c['description'][:80]}"
            for c in list_chart_instructions()
        ),
        shared=instruction_ctx.split("### ")[-1] if "### " in instruction_ctx else "",
        MAX_ICON_INCH=_MAX_ICON_INCH,
    )


def build_user_prompt(
    slide: dict,
    style: dict | None,
    template: dict | None,
    query: str | None = None,
    *,
    existing_outputs: dict | None = None,
) -> str:
    """Build the user prompt for a single slide."""
    content_json = slide.get("content_json", {})
    if isinstance(content_json, str):
        try:
            content_json = json.loads(content_json)
        except json.JSONDecodeError:
            content_json = {}

    main_points = content_json.get("main_points", [])
    detailed = content_json.get("detailed_content", "")
    key_data = content_json.get("key_data", "")
    visual_note = content_json.get("visual_note", "")
    fmt = content_json.get("recommended_ppt_format", "bullet_list")

    detailed_block = f"详细内容: {detailed}" if detailed else ""
    key_data_block = f"关键数据: {key_data}" if key_data else ""
    visual_note_block = f"可视化建议: {visual_note}" if visual_note else ""

    existing_section = _build_existing_section(existing_outputs) if existing_outputs else ""
    color_section = _build_style_section(style) if style else "## 配色方案: 使用默认配色"
    template_section = _build_template_section(template) if template else ""
    query_section = f"## 修改指令\n{query}" if query else ""

    template_text = _load_prompt("content_agent_user.md")
    return template_text.format(
        slide_title=slide.get("title", ""),
        slide_layout_type=slide.get("layout_type", "content"),
        recommended_format=fmt,
        has_chart=slide.get("has_chart", False),
        has_image=slide.get("has_image", False),
        main_points=_j(main_points),
        detailed_content_block=detailed_block,
        key_data_block=key_data_block,
        visual_note_block=visual_note_block,
        existing_content_section=existing_section,
        color_scheme_section=color_section,
        template_section=template_section,
        neighbor_section=query_section,
    )


def _build_style_section(data: dict) -> str:
    parts = [
        "## 配色方案",
        f"名称: {data.get('label', '')} ({data.get('name', '')})",
        f"风格密度: {data.get('style_density', 'moderate')}",
    ]
    colors = data.get("colors", {})
    parts.append(
        f"颜色: primary={colors.get('primary')}, accent={colors.get('accent')}, "
        f"text={colors.get('text')}, bg={colors.get('bg')}, border={colors.get('border')}"
    )
    chart_colors = data.get("chart_colors", [])
    if chart_colors:
        parts.append(f"图表色: {', '.join(chart_colors[:6])}")
    fonts = data.get("fonts", {})
    if fonts:
        parts.append(
            f"字体: h1({fonts.get('h1',{}).get('size','?')}pt) "
            f"h2({fonts.get('h2',{}).get('size','?')}pt) "
            f"body({fonts.get('body',{}).get('size','?')}pt) "
            f"最小: {fonts.get('min_size','?')}pt"
        )

    # Background (full JSON, not summarized)
    bg = data.get("background_json", {})
    if bg:
        parts.append(f"背景预设: {_j(bg)}")
        parts.append("可沿用此预设，也可自行重新设计背景。")

    parts.append(_Z_ORDER_TABLE)
    return "\n".join(parts)


def _build_existing_section(outputs: dict) -> str:
    """Pass existing slide state as raw JSON — do NOT parse or truncate."""
    return (
        "## 当前 slide 已有内容（修改模式，完整 JSON）\n"
        "你可以保留、修改或删除已有元素。删除用 submit_element(element_id=..., delete=true)。\n"
        "```json\n"
        + json.dumps(outputs, ensure_ascii=False, indent=2)
        + "\n```"
    )


def _build_template_section(template: dict) -> str:
    if not template:
        return ""

    parts = ["## 布局模板（参考，不必严格遵循）"]
    if template:
        name = template.get("name", "")
        label = template.get("label", "")
        parts.append(f"模板: {name} ({label})")
        containers = template.get("containers", [])
        if containers:
            parts.append(f"容器区域: {', '.join(c['id'] for c in containers)}")
        fixed = template.get("fixed_elements", [])
        if fixed:
            parts.append(f"固定元素: {len(fixed)} 个")
    parts.append("模板中的布局和元素仅供参考，你可以自由设计。")
    return "\n".join(parts)


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
