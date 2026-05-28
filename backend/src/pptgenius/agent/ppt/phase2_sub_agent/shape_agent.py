"""ShapeAgent — generates decorative shape elements for title/section/ending pages.

Uses create_agent with tools: submit_shape_elements.
Reads instructions: shape.json, shape_catalog.json, shared/*.json
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.agent.outline.middleware import TokenCountingMiddleware
from pptgenius.agent.ppt.common.instruction_loader import get_instruction, get_shared_instructions
from pptgenius.agent.ppt.common.tools import (
    _make_submit_shape_elements,
)
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.agent.ppt.shape_agent")
apply_deepseek_patch()


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model, base_url=cfg.base_url, api_key=cfg.api_key,
        temperature=0.3, max_tokens=6000,
    )


async def run_shape_agent(
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
    """Generate decorative shape elements for one slide."""

    submit_tool = _make_submit_shape_elements(db, presentation_id, slide_index)
    tools = [submit_tool]

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
    _log.info("ShapeAgent done for slide %d", slide_index)


def _build_system_prompt() -> str:
    shape_inst = get_instruction("shape.json")
    catalog = get_instruction("shape_catalog.json")
    shared = get_shared_instructions("position", "fill", "line", "font")

    # Extract commonly useful shapes from catalog
    groups = catalog.get("groups", {})
    shape_summary = []
    for gname, gdata in groups.items():
        shapes = list(gdata.get("shapes", {}).keys())[:6]
        shape_summary.append(f"- {gdata['label']}: {', '.join(shapes)}")

    return f"""你是 PPT 装饰形状生成器。为页面生成美观的装饰性 shape 元素。

## 指令文件

### shape.json
```json
{_j(shape_inst)}
```

## 常用形状速查

{chr(10).join(shape_summary)}

{shared}

## 页面类型与形状建议

| 页面 | 建议 |
|------|------|
| title_slide (封面) | 大面积几何装饰、飘带(up_ribbon)、箭头、圆角矩形背景 |
| section (章节) | 圆形/六边形放章节号、分隔线、渐变填充背景 |
| ending (结尾) | 致谢背景框(rounded_rectangle)、装饰性星形、心形 |
| content_* | Container 圆角背景框、标题装饰条 |

## 规则

- 形状可以带文字（text 字段），用于章节号/标题叠加
- 使用 color_scheme 中的 primary / accent / border 颜色
- **必须调用 submit_shape_elements 提交**
"""


def _build_user_prompt(slide: dict, layout_name: str, container_bounds: dict) -> str:
    parts = [
        f"## 页面信息",
        f"标题: {slide.get('title', '')}",
        f"layout_type: {slide.get('layout_type', '')}",
        f"PPT 布局: {layout_name}",
        f"\n请根据页面类型生成合适的装饰形状元素。",
    ]
    return "\n".join(parts)


def _j(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
