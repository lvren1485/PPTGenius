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
    pres_status: str | None = None,
    plan: dict | None = None,
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
    query_section = str(query) if query else ""
    status_hints = {
        "o_modified_modify": "用户要求修改本页内容",
        "o_modified_merge":  "本页内容来自被删除页面合并，需要重新组织",
        "o_modified_split":  "本页从其他页面复制/拆分，需要调整为独立内容",
        "o_modified_new":    "本页是新插入的页面，需要从零填充内容",
    }
    status_section = ""
    if pres_status and pres_status in status_hints:
        status_section = f"## 页面状态\n{status_hints[pres_status]} (status={pres_status})"

    plan_section = _build_plan_section(plan) if plan else ""

    # Section info — for section-type slides, tell the agent which section this is
    section_info = ""
    sec_idx = slide.get("section_index")
    sec_title = slide.get("section_title")
    if sec_idx is not None:
        section_info = f"## 章节信息\n这是第 **{sec_idx}** 节"
        if sec_title:
            section_info += f"：{sec_title}"

    template_text = _load_prompt("content_agent_user.md")
    return template_text.format(
        slide_title=slide.get("title", ""),
        slide_index=slide.get("slide_index", 0),
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
        neighbor_section=query_section,  # now at top of prompt as "⚡ 修改指令"
        status_section=status_section,
        plan_section=plan_section,
        section_info=section_info,
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
        def _fs(key: str) -> str:
            v = fonts.get(key, "?")
            if isinstance(v, dict):
                return str(v.get("size", "?"))
            return str(v) if v != "?" else "?"
        parts.append(
            f"字体: h1({_fs('h1')}pt) "
            f"h2({_fs('h2')}pt) "
            f"body_title({_fs('body_title')}pt) "
            f"body({_fs('body')}pt) "
            f"body_small({_fs('body_small')}pt) "
            f"caption({_fs('caption')}pt)"
        )

    # Text density
    td = data.get("text_density", "moderate")
    td_hints = {
        "sparse": "稀疏: 1-2 个 textbox，内容精简",
        "moderate": "适中: 2-4 个 textbox，正常内容量",
        "dense": "密集: 5-6 个 textbox，可容纳较多文字",
    }
    parts.append(f"文本密度: {td} — {td_hints.get(td, td_hints['moderate'])}")

    # Background (full JSON, not summarized)
    bg = data.get("background_json", {})
    if bg:
        parts.append(f"背景预设: {_j(bg)}")
        parts.append("可沿用此预设，也可自行重新设计背景。")

    return "\n".join(parts)


def _build_existing_section(outputs: dict) -> str:
    """Compact summary table — full details available via check_parts()."""
    elements = outputs.get("elements", [])
    if not elements:
        return ""

    lines = [
        "## 当前 slide 已有元素（修改模式）",
        f"共 {len(elements)} 个元素。使用 `_eid` 精确覆盖或删除。",
        f"背景类型: {outputs.get('background', {}).get('type', '未设置')}",
        "",
        "| _eid | type | 子类型 | part | left | top | w×h | 内容摘要 |",
        "|------|------|--------|------|------|-----|-----|---------|",
    ]
    for el in elements:
        pos = el.get("position", {})
        eid = (el.get("_eid") or el.get("id") or "-")[:8]
        el_type = el.get("type", "?")
        subtype = el.get("shape_type") or el.get("chart_type") or "-"
        part = el.get("_part", "-")
        left = pos.get("left", 0)
        top = pos.get("top", 0)
        w = pos.get("width", 0)
        h = pos.get("height") or 0
        # Content hint: first 30 chars of text
        hint = ""
        if el_type == "textbox":
            for block in el.get("content", []):
                for run in block.get("paragraph", {}).get("runs", []):
                    hint = run.get("text", "")[:30]
                    break
                if hint:
                    break
        elif el_type == "chart":
            hint = el.get("title", "")[:30] or el.get("chart_type", "")
        elif el_type == "table":
            hint = f"{el.get('rows', 0)}×{el.get('cols', 0)}"
        elif el_type == "picture":
            hint = el.get("name", "") or el.get("path", "") or ""
            hint = hint[:30]
        lines.append(
            f"| {eid} | {el_type} | {subtype} | {part} "
            f"| {left:.1f} | {top:.1f} | {w:.1f}×{h:.1f} | {hint} |"
        )
    lines.append("")
    lines.append("**操作**: 覆盖=`submit_element(element_id=_eid, element={{...}}, part=...)`，删除=`submit_element(element_id=_eid, delete=true)`")
    lines.append("详情用 `check_parts(part=\"xxx\")` 查看。")
    return "\n".join(lines)


def _build_template_section(template: dict) -> str:
    if not template:
        return ""

    lines = [
        "## 布局模板参考坐标（仅供参考，你可以自由设计）",
        f"模板类型: {template.get('type', '')} — {template.get('description', '')}",
        "",
        "| id | 类型 | left | top | width | height | 说明 |",
        "|----|------|------|-----|-------|--------|------|",
    ]
    for el in template.get("elements", []):
        pos = el.get("position", {})
        lines.append(
            f"| {el.get('id', '-')} | {el.get('type', '-')} "
            f"| {pos.get('left', '-')} | {pos.get('top', '-')} "
            f"| {pos.get('width', '-')} | {pos.get('height', '-')} "
            f"| {el.get('remark', '-')} |"
        )
    lines.append("")
    lines.append("模板仅供参考，你可以自由设计。")
    return "\n".join(lines)


def _build_plan_section(plan: dict) -> str:
    """Format the part-based plan for injection into the user prompt."""
    if not plan or not plan.get("parts"):
        return ""
    parts = plan["parts"]
    decor = plan.get("decor_style", "")
    lines = [
        "## 设计计划 (Plan)",
        f"设计概念: {plan.get('design_concept', '')}",
    ]
    if decor:
        lines.append(f"装饰风格 (已锁定): **{decor}** — 不能再使用 {'icon' if decor == 'emoji' else 'emoji'}")
    lines.append("")
    lines.extend(["| Part | 状态 | 描述 |", "|------|------|------|"])
    for name, info in parts.items():
        status = info.get("status", "pending")
        desc = info.get("description", "")[:80]
        status_mark = "✓" if status == "complete" else "○"
        lines.append(f"| {status_mark} {name} | {status} | {desc} |")
    lines.append("")
    lines.append("**修改 Plan**：重新调用 submit_plan，同名 part 会更新描述并重置为 pending，新名称会追加。")
    return "\n".join(lines)


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
