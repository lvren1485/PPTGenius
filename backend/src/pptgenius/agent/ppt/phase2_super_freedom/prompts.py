"""Super-Freedom prompt builder — loads templates from resources/prompts/ppt/
and fills placeholders with instruction files / slide data / color scheme info.
"""

from __future__ import annotations

import json
from pathlib import Path

from pptgenius.agent.ppt.common.instruction_loader import (
    get_how_to_read,
    get_instruction,
    get_shared_instructions,
    list_chart_instructions,
)
from pptgenius.infrastructure.config import RESOURCES_DIR

_PROMPTS_DIR = RESOURCES_DIR / "prompts" / "ppt"

# 2cm in inches
_MAX_ICON_INCH = 0.79


def _load_txt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt template not found: {path}")


def build_system_prompt() -> str:
    howto = get_how_to_read()
    textbox_inst = _j(get_instruction("textbox.json"))
    table_inst = _j(get_instruction("table.json"))
    picture_inst = _j(get_instruction("picture.json"))
    shape_inst = _j(get_instruction("shape.json"))
    background_inst = _j(get_instruction("background.json"))

    charts = list_chart_instructions()
    chart_list = "\n".join(
        f"- `{c['chart_type']}`: {c['description'][:80]}" for c in charts
    )
    shared = get_shared_instructions("position", "font", "fill", "line")

    template = _load_txt("super_freedom_system.txt")
    return template.format(
        howto=howto,
        textbox_inst=textbox_inst,
        table_inst=table_inst,
        picture_inst=picture_inst,
        shape_inst=shape_inst,
        background_inst=background_inst,
        chart_list=chart_list,
        shared=shared,
        MAX_ICON_INCH=_MAX_ICON_INCH,
    )


def build_user_prompt(
    slide: dict,
    selected_layouts: dict[str, dict],
    color_scheme_data: dict,
) -> str:
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

    detailed_block = f"详细内容: {detailed[:2000]}" if detailed else ""
    key_data_block = f"关键数据: {key_data}" if key_data else ""
    visual_note_block = f"可视化建议: {visual_note}" if visual_note else ""

    color_section = _build_color_section(color_scheme_data)
    template_section = _build_template_section(selected_layouts)
    neighbor_section = _build_neighbor_section(slide)

    template = _load_txt("super_freedom_user.txt")
    return template.format(
        slide_title=slide.get("title", ""),
        slide_layout_type=slide.get("layout_type", "content"),
        recommended_format=fmt,
        has_chart=slide.get("has_chart", False),
        has_image=slide.get("has_image", False),
        main_points=_j(main_points),
        detailed_content_block=detailed_block,
        key_data_block=key_data_block,
        visual_note_block=visual_note_block,
        color_scheme_section=color_section,
        template_section=template_section,
        neighbor_section=neighbor_section,
    )


def _build_color_section(data: dict) -> str:
    if not data:
        return "## 配色方案: 使用默认配色"

    parts = [
        "## 配色方案（参考）",
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
            f"字体层级: h1({fonts.get('h1',{}).get('size','?')}pt) "
            f"h2({fonts.get('h2',{}).get('size','?')}pt) "
            f"h3({fonts.get('h3',{}).get('size','?')}pt) "
            f"body({fonts.get('body',{}).get('size','?')}pt) "
            f"最小字号: {fonts.get('min_size','?')}pt"
        )
    return "\n".join(parts)


def _build_template_section(layouts: dict[str, dict]) -> str:
    if not layouts:
        return ""

    parts = ["## 模板参考（仅供参考，不必严格遵循）"]
    layout_names = list(layouts.keys())
    parts.append(f"可用布局: {', '.join(layout_names[:7])}")
    for ln in layout_names[:2]:
        ld = layouts.get(ln, {})
        if ld:
            parts.append(f"\n### {ln} 布局概要")
            parts.append(f"固定元素: {len(ld.get('fixed_elements', []))} 个")
            parts.append(f"装饰: {len(ld.get('decorations', []))} 个")
            containers = ld.get("containers", [])
            if containers:
                parts.append(f"容器: {len(containers)} 个 ({', '.join(c['id'] for c in containers)})")
    parts.append("\n模板中的装饰元素、容器分区仅作为设计灵感来源。")
    parts.append("你可以自由设计背景、元素位置和数量，发挥创意。")
    return "\n".join(parts)


def _build_neighbor_section(slide: dict) -> str:
    neighbor = slide.get("_neighbor_context", "")
    if not neighbor:
        return ""
    return f"## 相邻页面上下文\n{neighbor}"


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
