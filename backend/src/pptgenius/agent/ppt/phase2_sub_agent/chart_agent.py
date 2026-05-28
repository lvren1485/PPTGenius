"""ChartAgent — generates chart elements based on slide data.

Uses create_agent with tools: read_chart_instruction, submit_chart_element.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.agent.outline.middleware import TokenCountingMiddleware
from pptgenius.agent.ppt.common.instruction_loader import get_shared_instructions, list_chart_instructions
from pptgenius.agent.ppt.common.tools import (
    _make_read_chart_instruction,
    _make_submit_chart_element,
)
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.agent.ppt.chart_agent")
apply_deepseek_patch()


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model, base_url=cfg.base_url, api_key=cfg.api_key,
        temperature=0.2, max_tokens=8000,
    )


async def run_chart_agent(
    *,
    db: Database,
    slide: dict,
    container_bounds: dict,
    presentation_id: int,
    slide_index: int,
    color_scheme_id: int | None,
    conv_id: int,
    config: RunnableConfig,
) -> None:
    """Generate a chart element for one slide."""

    submit_tool = _make_submit_chart_element(db, presentation_id, slide_index)
    tools = [
        _make_read_chart_instruction(),
        submit_tool,
    ]

    system_prompt = _build_chart_system_prompt()
    user_prompt = _build_chart_user_prompt(slide, container_bounds)

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
    _log.info("ChartAgent done for slide %d", slide_index)


def _build_chart_system_prompt() -> str:
    charts = list_chart_instructions()
    chart_list = "\n".join(
        f"- `{c['chart_type']}`: {c['description'][:80]}" for c in charts
    )
    shared = get_shared_instructions("position", "font")

    return f"""你是 PPT 图表生成器。根据数据选择合适的图表类型并生成 chart 元素。

## 可用图表类型

{chart_list}

## 选择规则

- 分类对比（看绝对值）→ column_clustered
- 分类标签长（>4个汉字）→ bar_clustered
- 时间序列趋势 → line / line_markers
- 占比/份额 → pie / doughnut（仅1个series）
- 两个数值变量关系 → scatter
- 多维度评分（≥3维）→ radar
- 三变量（x+y+大小）→ bubble
- 累积趋势 → area

{shared}

## 工作流程

1. 分析数据特征 → 确定 chart_type
2. 调用 read_chart_instruction(chart_type) 读取该类型的完整字段定义
3. 按照指令文件生成 chart 元素 JSON
4. **必须调用 submit_chart_element 提交验证**

## 图表配色

使用提供的 chart_colors（按 series 顺序使用）。

## 注意事项

- pie/doughnut 只支持 1 个 series
- series.values 长度必须 = categories 长度
- chart_type 必须精确匹配（如 column_clustered 不是 column）
"""


def _build_chart_user_prompt(slide: dict, container_bounds: dict) -> str:
    content_json = slide.get("content_json", {})
    if isinstance(content_json, str):
        import json
        try:
            content_json = json.loads(content_json)
        except json.JSONDecodeError:
            content_json = {}

    key_data = content_json.get("key_data", "")
    main_points = content_json.get("main_points", [])
    fmt = content_json.get("recommended_ppt_format", "")

    parts = [
        f"## 数据",
        f"页面标题: {slide.get('title', '')}",
    ]
    if key_data:
        parts.append(f"关键数据: {key_data}")
    if main_points:
        parts.append(f"要点: {_j(main_points)}")
    if fmt:
        parts.append(f"推荐格式: {fmt}")

    # Container info
    parts.append(f"\n## 容器信息")
    for cid, b in container_bounds.items():
        if cid == "slide":
            continue
        parts.append(
            f"容器 '{cid}': left={b['left']}, top={b['top']}, "
            f"width={b['width']}, height={b['height']}"
        )
        parts.append(f"使用相对坐标，position.parent='{cid}'")
        break  # chart goes in first available container

    if not any(cid != "slide" for cid in container_bounds):
        parts.append("无容器分区。图表适合放在: left=0.8, top=1.6, width=8.5, height=5.0")

    parts.append(f"\n请选择合适的图表类型，读取对应指令文件，生成图表元素。")
    return "\n".join(parts)


def _j(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)
