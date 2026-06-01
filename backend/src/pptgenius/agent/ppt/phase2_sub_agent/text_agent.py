"""TextAgent — generates textbox, table, and picture (icon) elements.

Uses create_agent with tools: search_icons, submit_text_elements.
Reads instructions: textbox.json, table.json, picture.json, shared/*.json
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.agent.outline.middleware import TokenCountingMiddleware
from pptgenius.agent.ppt.common.instruction_loader import get_how_to_read, get_instruction, get_shared_instructions
from pptgenius.agent.ppt.common.tools import (
    _make_search_icons,
    _make_submit_text_elements,
)
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.agent.ppt.text_agent")
apply_deepseek_patch()


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model, base_url=cfg.base_url, api_key=cfg.api_key,
        temperature=0.3, max_tokens=8000,
    )


async def run_text_agent(
    *,
    db: Database,
    slide: dict,
    layout_name: str,
    container_bounds: dict,
    presentation_id: int,
    slide_index: int,
    color_scheme_id: int | None,
    conv_id: int,
    config: RunnableConfig,
) -> None:
    """Generate text/table/icon elements for one slide."""

    submit_tool = _make_submit_text_elements(db, presentation_id, slide_index)
    tools = [
        _make_search_icons(),
        submit_tool,
    ]

    # Build system prompt with instructions
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(slide, layout_name, container_bounds)

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
    _log.info("TextAgent done for slide %d", slide_index)


def _build_system_prompt() -> str:
    howto = get_how_to_read()
    textbox_inst = get_instruction("textbox.json")
    table_inst = get_instruction("table.json")
    pic_inst = get_instruction("picture.json")
    shared = get_shared_instructions("position", "font", "line")

    return f"""{howto}

你是 PPT 文本内容生成器。根据大纲 slide 的 content_json 生成 textbox / table / picture (SVG icon) 元素。

## 指令文件

### textbox.json
```json
{_json(textbox_inst)}
```

### table.json
```json
{_json(table_inst)}
```

### picture.json (SVG图标)
```json
{_json(pic_inst)}
```

{shared}

## 工作流程

1. 分析 outline slide 的 content_json（main_points, detailed_content, key_data）
2. 如果数据适合表格展示 → 生成 table 元素
3. 如果要点适合用图标装饰 → search_icons 搜索 → 选 icon name → picture 元素
   ⚠️ SVG 图标尺寸限制: width/height 均 ≤0.79 inch (2cm)。更大装饰用 textbox 特殊字符或交给 shape agent 处理。
4. 生成 textbox 元素放置标题和正文
5. **必须调用 submit_text_elements 提交**

## 颜色

使用提供的 color_scheme 中的字体颜色。如果没有提供，使用默认色。

## container 可用图片素材: [] (无)
如有 has_image 标记但无可用素材，在 content 中加备注。
"""


def _build_user_prompt(slide: dict, layout_name: str, container_bounds: dict) -> str:
    content_json = slide.get("content_json", {})
    if isinstance(content_json, str):
        import json
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
        f"## Outline Slide 信息",
        f"标题: {slide.get('title', '')}",
        f"layout_type: {slide.get('layout_type', 'content')}",
        f"页面布局: {layout_name}",
        f"recommended_ppt_format: {fmt}",
        f"has_image: {slide.get('has_image', False)}",
        f"has_chart: {slide.get('has_chart', False)}",
    ]
    if main_points:
        parts.append(f"核心要点: {_json(main_points)}")
    if detailed:
        parts.append(f"详细内容: {detailed}")
    if key_data:
        parts.append(f"关键数据: {key_data}")
    if visual_note:
        parts.append(f"可视化建议: {visual_note}")

    # Container bounds context
    parts.append(f"\n## 容器信息")
    if container_bounds and len(container_bounds) > 1:
        for cid, b in container_bounds.items():
            if cid == "slide":
                continue
            parts.append(
                f"容器 '{cid}': left={b['left']}, top={b['top']}, "
                f"width={b['width']}, height={b['height']}"
            )
        parts.append("使用相对坐标，position.parent 设为容器 id。")
    else:
        parts.append("无容器分区，使用绝对坐标（整个 slide 13.333×7.5 英寸）。")

    # Neighbor context for cross-slide awareness
    neighbor = slide.get("_neighbor_context", "")
    if neighbor:
        parts.append(f"\n## 相邻页面上下文\n{neighbor}")

    parts.append(f"\n请生成该页的文本/表格/图标元素。如果数据适合表格展示，优先使用 table。")
    return "\n".join(parts)


def _json(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
