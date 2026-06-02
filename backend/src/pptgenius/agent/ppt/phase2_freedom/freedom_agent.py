"""FreedomAgent — one agent generates ALL elements for a slide at once.

Receives the complete instruction set (all *.json files), outline slide data,
layout + container bounds, and color scheme info.
"""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
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
    _make_submit_slide_elements,
)
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.agent.ppt.freedom_agent")
apply_deepseek_patch()


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model, base_url=cfg.base_url, api_key=cfg.api_key,
        temperature=0.3, max_tokens=16000,
    )


async def run_freedom_agent(
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
    """Generate all elements for one slide in a single agent call."""

    submit_tool = _make_submit_slide_elements(db, presentation_id, slide_index)
    tools = [
        _make_search_icons(),
        _make_read_instruction(),
        submit_tool,
    ]

    system_prompt = _build_freedom_system_prompt()
    user_prompt = _build_freedom_user_prompt(slide, layout_name, container_bounds)

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
    _log.info("FreedomAgent done for slide %d", slide_index)


def _build_freedom_system_prompt() -> str:
    """Build system prompt with ALL instruction summaries."""
    howto = get_how_to_read()
    background = get_instruction("background.json")
    textbox = get_instruction("textbox.json")
    table = get_instruction("table.json")
    picture = get_instruction("picture.json")
    shape = get_instruction("shape.json")

    charts = list_chart_instructions()
    chart_list = "\n".join(
        f"- `{c['chart_type']}`: {c['description'][:80]}" for c in charts
    )

    shared = get_shared_instructions("position", "font", "fill", "line")

    return f"""{howto}

你是 PPT 整页生成器（Freedom 模式）。为一张幻灯片生成所有元素（textbox/table/chart/shape/picture）。

## 元素指令摘要

### textbox — 文本框（最常用）
type="textbox", content 是 paragraph 数组，每个 paragraph 含 runs。

### table — 表格
type="table", rows>0, cols>0, cells 数组（row/col/text）。

### picture — 图标（SVG）
type="picture", name+color 模式（search_icons 搜索后选取）。

### shape — 装饰形状
type="shape", shape_type 从 182 种中选择。

### background — 幻灯片背景
slide 级别（非 element）。

## 图表类型选择

{chart_list}

## 规则

{shared}

## 工作流程

1. 分析 outline slide 的 content_json
2. 如果有图表数据 → read_instruction("chart/column.json") 等
3. 搜索 SVG 图标 → search_icons（⚠️ SVG 图标尺寸 ≤0.79 inch/2cm，更大用 shape）
4. 生成所有元素 → submit_slide_elements 提交
"""


def _build_freedom_user_prompt(
    slide: dict, layout_name: str, container_bounds: dict
) -> str:
    content_json = slide.get("content_json", {})
    if isinstance(content_json, str):
        try:
            content_json = json.loads(content_json)
        except json.JSONDecodeError:
            content_json = {}

    parts = [
        f"## Slide 信息",
        f"标题: {slide.get('title', '')}",
        f"layout_type: {slide.get('layout_type', 'content')}",
        f"布局: {layout_name}",
        f"has_chart: {slide.get('has_chart', False)}",
        f"has_image: {slide.get('has_image', False)}",
        "",
        f"## content_json",
        json.dumps(content_json, ensure_ascii=False, indent=2),
        "",
        f"## 容器信息",
    ]

    for cid, b in container_bounds.items():
        if cid == "slide":
            continue
        parts.append(
            f"容器 '{cid}': left={b['left']}, top={b['top']}, "
            f"width={b['width']}, height={b['height']}"
        )
        parts.append(f"container 内元素使用相对坐标，position.parent='{cid}'")

    if not any(cid != "slide" for cid in container_bounds):
        parts.append("无容器分区，使用绝对坐标（13.333x7.5 英寸）。")

    parts.append("\n请生成该页的所有元素。先 read_instruction 获取需要的指令，再生成 JSON，最后 submit_slide_elements 提交。")
    return "\n".join(parts)
