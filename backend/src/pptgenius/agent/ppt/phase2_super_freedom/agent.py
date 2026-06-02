"""SuperFreedomAgent — full creative control per slide.

Generates a complete slide instruction (background + all elements + notes)
without template enforcement. Template/color info is reference only.
"""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.agent.outline.middleware import TokenCountingMiddleware
from pptgenius.agent.ppt.common.instruction_loader import (
    get_how_to_read,
    get_instruction,
    get_shared_instructions,
    list_chart_instructions,
)
from pptgenius.agent.ppt.common.tools import (
    _make_search_icons,
    _make_read_instruction,
)
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.agent.ppt.super_freedom")
apply_deepseek_patch()

# 2cm in inches
_MAX_ICON_INCH = 0.79


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model, base_url=cfg.base_url, api_key=cfg.api_key,
        temperature=0.3, max_tokens=16000,
    )


def _make_submit_slide_instruction(db: Database, presentation_id: int, slide_index: int):
    """Submit a complete slide instruction — validates then stores."""

    @tool
    async def submit_slide_instruction(
        background: dict,
        elements: list[dict],
        notes: str = "",
    ) -> str:
        """Submit a complete slide design (background + all elements + notes).

        This is the terminal action — call it when the slide is fully designed.

        Parameters
        ----------
        background : dict — Slide background. e.g. {"type":"solid","color":"F8FAFC"}
            or {"type":"gradient","gradient_angle":135,"gradient_stops":[...]}
        elements : list[dict] — All elements (textbox/table/chart/picture/shape).
            Each must pass schema validation.
        notes : str — Speaker notes for this slide.
        """
        from pptgenius.infrastructure.ppt_engine.validator import validate_elements

        # Validate all elements
        result = validate_elements(elements)
        if not result.is_valid:
            error_details = "\n".join(
                f"  - [{e['path']}] {e['error']}" for e in result.errors[:15]
            )
            return (
                f"❌ 校验失败 ({len(result.errors)} 个错误):\n{error_details}\n"
                f"请根据错误修正后重新提交。"
            )

        # Validate background
        if background:
            bg_type = background.get("type", "")
            if bg_type not in ("solid", "gradient", "image", "no_fill"):
                return f"❌ background.type 无效: '{bg_type}'。有效值: solid, gradient, image, no_fill"
            if bg_type == "gradient" and not background.get("gradient_stops"):
                return "❌ gradient 背景必须包含 gradient_stops。"

        # Store as complete slide instruction
        await db.set_slide_agent_output(
            presentation_id=presentation_id,
            slide_index=slide_index,
            agent_type="super_freedom",
            output={
                "background": background,
                "elements": elements,
                "notes": notes,
            },
        )

        return (
            f"✅ 已保存完整 slide 设计: {len(elements)} 个元素, "
            f"background={background.get('type', 'none')}, notes={len(notes)} chars"
        )

    return submit_slide_instruction


async def run_super_freedom_agent(
    *,
    db: Database,
    slide: dict,
    selected_layouts: dict[str, dict],
    presentation_id: int,
    slide_index: int,
    color_scheme_id: int | None,
    conv_id: int,
    config: RunnableConfig,
) -> None:
    """Generate a complete slide instruction — full creative control."""

    # Load color scheme data
    color_scheme_data: dict = {}
    if color_scheme_id:
        cs = await db.get_color_scheme(color_scheme_id)
        if cs:
            color_scheme_data = {
                "id": cs.id,
                "name": cs.name,
                "label": cs.label,
                "colors": cs.colors_json,
                "chart_colors": cs.chart_colors_json,
                "fonts": cs.fonts_json,
                "style_density": getattr(cs, "style_density", "moderate"),
            }

    submit_tool = _make_submit_slide_instruction(db, presentation_id, slide_index)
    tools = [
        _make_search_icons(),
        _make_read_instruction(),
        submit_tool,
    ]

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(slide, selected_layouts, color_scheme_data)

    agent = create_agent(
        model=_get_model(),
        tools=tools,
        system_prompt=system_prompt,
        middleware=[TokenCountingMiddleware(conv_id)],
    )

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config=config,
    )
    _log.info("SuperFreedomAgent done for slide %d", slide_index)


def _build_system_prompt() -> str:
    howto = get_how_to_read()
    textbox_inst = get_instruction("textbox.json")
    table_inst = get_instruction("table.json")
    picture_inst = get_instruction("picture.json")
    shape_inst = get_instruction("shape.json")
    background_inst = get_instruction("background.json")

    charts = list_chart_instructions()
    chart_list = "\n".join(
        f"- `{c['chart_type']}`: {c['description'][:80]}" for c in charts
    )
    shared = get_shared_instructions("position", "font", "fill", "line")

    return f"""{howto}

你是 PPT 自由设计师（Super-Freedom 模式）。为一张幻灯片从头设计完整的视觉方案。

## 核心原则

你拥有完全的创作自由。模板仅作为灵感参考，你可以自由决定背景、元素位置、数量和风格。

## 元素指令集

### textbox.json — 文本框
```json
{_j(textbox_inst)}
```

### table.json — 表格
```json
{_j(table_inst)}
```

### picture.json — SVG 图标
```json
{_j(picture_inst)}
```

### shape.json — 形状装饰
```json
{_j(shape_inst)}
```

### background.json — 背景
```json
{_j(background_inst)}
```

{shared}

## 图表类型选择

{chart_list}

**规则**: pie/doughnut 仅支持 1 个 series。columns/chart_type 必须精确匹配。

## 设计要素

1. **背景**: solid(纯色)/gradient(渐变)/image(图片)。大胆使用渐变色营造氛围。
2. **文本框**: 标题(h1/h2)、正文(body 16pt)、辅助文字(caption 14pt)。**所有字号 >= 14pt**。
3. **形状装饰**: 矩形、圆角矩形、线条等。用于分隔区域、强调重点、装饰背景。
4. **图表**: 如果 slide 有图表数据，选择合适的图表类型并生成。
5. **SVG 图标**: 装饰性小图标（⚠️ 尺寸 ≤{_MAX_ICON_INCH} inch / 2cm）。更大装饰用 shape。
6. **备注**: 写入演讲者备注。

## 完整 Slide 设计示例

以下是一个 title_slide（封面页）的完整设计：

```json
{{
  "background": {{
    "type": "gradient",
    "gradient_angle": 135,
    "gradient_stops": [
      {{"position": 0, "color": "1a237e"}},
      {{"position": 0.5, "color": "283593"}},
      {{"position": 1.0, "color": "3949ab"}}
    ]
  }},
  "notes": "封面页——用深蓝渐变营造科技感，副标题说明演讲主题，装饰条增加视觉层次。",
  "elements": [
    {{
      "type": "shape",
      "shape_type": "rectangle",
      "position": {{"left": 0, "top": 0, "width": 13.333, "height": 0.08}},
      "fill": {{"type": "solid", "color": "5c6bc0"}}
    }},
    {{
      "type": "shape",
      "shape_type": "rectangle",
      "position": {{"left": 0, "top": 6.8, "width": 13.333, "height": 0.7}},
      "fill": {{"type": "solid", "color": "1a237e"}}
    }},
    {{
      "type": "shape",
      "shape_type": "rounded_rectangle",
      "position": {{"left": 0.8, "top": 2.0, "width": 0.12, "height": 3.5}},
      "fill": {{"type": "solid", "color": "5c6bc0"}}
    }},
    {{
      "type": "textbox",
      "position": {{"left": 1.2, "top": 1.8, "width": 11.0, "height": 1.5}},
      "content": [
        {{
          "paragraph": {{
            "alignment": "left",
            "runs": [
              {{"text": "人工智能时代的机遇与挑战", "font": {{"size": 40, "bold": true, "color": "ffffff"}}}}
            ]
          }}
        }}
      ]
    }},
    {{
      "type": "textbox",
      "position": {{"left": 1.2, "top": 3.4, "width": 10.5, "height": 0.8}},
      "content": [
        {{
          "paragraph": {{
            "alignment": "left",
            "runs": [
              {{"text": "从深度学习到大语言模型 — 2025年技术前沿展望", "font": {{"size": 18, "color": "b3c6ff"}}}}
            ]
          }}
        }}
      ]
    }},
    {{
      "type": "textbox",
      "position": {{"left": 1.2, "top": 5.0, "width": 5.0, "height": 0.6}},
      "content": [
        {{
          "paragraph": {{
            "alignment": "left",
            "runs": [
              {{"text": "张三 · 2025年6月", "font": {{"size": 14, "color": "7986cb"}}}}
            ]
          }}
        }}
      ]
    }},
    {{
      "type": "picture",
      "position": {{"left": 0.4, "top": 0.4, "width": 0.6, "height": 0.6}},
      "name": "cpu",
      "color": "5c6bc0",
      "fit": "aspect"
    }}
  ]
}}
```

## 设计要点

- 标题 h1(36pt)/h2(28pt) 大而醒目，正文 body(16pt)，辅助 caption(14pt)，**最小字号 14pt**
- 善用形状做装饰：分隔线、色块背景、强调边框
- 颜色保持协调——主色+辅色+点缀色，不超过 4 种
- SVG 图标仅作小装饰（≤{_MAX_ICON_INCH} inch），不要用作主体视觉
- 页面留白合理，不要过度拥挤（建议 6-15 个元素）
- 背景渐变色比纯色更有质感

## 工作流程

1. 分析 slide 的 content_json，确定页面类型和内容重点
2. 如需图表数据 → read_instruction("chart/...") 查看图表类型
3. 如需装饰图标 → search_icons("keyword") 搜索
4. 设计完整 slide → **必须调用 submit_slide_instruction 提交**
"""


def _build_user_prompt(
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

    parts = [
        f"## Slide 信息",
        f"标题: {slide.get('title', '')}",
        f"页面类型: {slide.get('layout_type', 'content')}",
        f"推荐格式: {fmt}",
        f"has_chart: {slide.get('has_chart', False)}",
        f"has_image: {slide.get('has_image', False)}",
        "",
        f"## outline content_json",
        f"核心要点: {_j(main_points)}",
    ]
    if detailed:
        parts.append(f"详细内容: {detailed[:2000]}")
    if key_data:
        parts.append(f"关键数据: {key_data}")
    if visual_note:
        parts.append(f"可视化建议: {visual_note}")

    # Full color scheme data
    if color_scheme_data:
        parts.append(f"\n## 配色方案（参考）")
        parts.append(f"名称: {color_scheme_data.get('label', '')} ({color_scheme_data.get('name', '')})")
        parts.append(f"风格密度: {color_scheme_data.get('style_density', 'moderate')}")
        colors = color_scheme_data.get("colors", {})
        parts.append(f"颜色: primary={colors.get('primary')}, accent={colors.get('accent')}, "
                     f"text={colors.get('text')}, bg={colors.get('bg')}, border={colors.get('border')}")
        chart_colors = color_scheme_data.get("chart_colors", [])
        if chart_colors:
            parts.append(f"图表色: {', '.join(chart_colors[:6])}")
        fonts = color_scheme_data.get("fonts", {})
        if fonts:
            parts.append(f"字体层级: h1({fonts.get('h1',{}).get('size','?')}pt) "
                         f"h2({fonts.get('h2',{}).get('size','?')}pt) "
                         f"h3({fonts.get('h3',{}).get('size','?')}pt) "
                         f"body({fonts.get('body',{}).get('size','?')}pt) "
                         f"最小字号: {fonts.get('min_size','?')}pt")
    else:
        parts.append(f"\n## 配色方案: 使用默认配色")

    # Template reference (inspiration only, not enforced)
    if selected_layouts:
        parts.append(f"\n## 模板参考（仅供参考，不必严格遵循）")
        layout_names = list(selected_layouts.keys())
        parts.append(f"可用布局: {', '.join(layout_names[:7])}")
        # Include one layout example
        for ln in layout_names[:2]:
            ld = selected_layouts.get(ln, {})
            if ld:
                parts.append(f"\n### {ln} 布局概要")
                parts.append(f"固定元素: {len(ld.get('fixed_elements', []))} 个")
                parts.append(f"装饰: {len(ld.get('decorations', []))} 个")
                containers = ld.get("containers", [])
                if containers:
                    parts.append(f"容器: {len(containers)} 个 ({', '.join(c['id'] for c in containers)})")
        parts.append("\n模板中的装饰元素、容器分区仅作为设计灵感来源。")
        parts.append("你可以自由设计背景、元素位置和数量，发挥创意。")

    # Neighbor context
    neighbor = slide.get("_neighbor_context", "")
    if neighbor:
        parts.append(f"\n## 相邻页面上下文\n{neighbor}")

    parts.append(
        f"\n## 画布尺寸\n"
        f"16:9 宽屏 = 13.333 × 7.5 inch。坐标系: 左上角为原点 (0,0)，"
        f"left 从左到右增大，top 从上到下增大。"
    )
    parts.append(
        f"\n请设计该页的完整视觉方案。"
        f"先思考背景和布局，再逐步生成元素，最后调用 submit_slide_instruction 提交。"
    )

    return "\n".join(parts)


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
