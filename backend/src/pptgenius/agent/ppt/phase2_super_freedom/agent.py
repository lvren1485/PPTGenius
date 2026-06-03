"""SuperFreedomAgent — full creative control per slide.

Generates a complete slide instruction (background + all elements + notes)
without template enforcement. Template/color info is reference only.
"""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.agent.outline.middleware import TokenCountingMiddleware
from pptgenius.agent.ppt.common.tools import (
    _make_search_icons,
    _make_read_instruction,
)
from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

from .prompts import build_system_prompt, build_user_prompt

_log = get_logger("pptgenius.agent.ppt.super_freedom")
apply_deepseek_patch()


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model, base_url=cfg.base_url, api_key=cfg.api_key,
        temperature=0.3, max_tokens=16000,
    )


def _make_submit_slide_instruction(db: Database, presentation_id: int, slide_index: int):
    """Submit a complete slide instruction — validates then stores.
    Returns (tool, was_called_getter) for retry detection."""

    _called: list[bool] = [False]

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
            await db.increment_slide_retry_by_index(presentation_id, slide_index)
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
                await db.increment_slide_retry_by_index(presentation_id, slide_index)
                return f"❌ background.type 无效: '{bg_type}'。有效值: solid, gradient, image, no_fill"
            if bg_type == "gradient" and not background.get("gradient_stops"):
                await db.increment_slide_retry_by_index(presentation_id, slide_index)
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
        _called[0] = True

        return (
            f"✅ 已保存完整 slide 设计: {len(elements)} 个元素, "
            f"background={background.get('type', 'none')}, notes={len(notes)} chars"
        )

    return submit_slide_instruction, _called


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
) -> bool:
    """Generate a complete slide instruction — full creative control.

    Returns True if submit_slide_instruction was called successfully.
    """

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

    submit_tool, was_called = _make_submit_slide_instruction(db, presentation_id, slide_index)
    tools = [
        _make_search_icons(),
        _make_read_instruction(),
        submit_tool,
    ]

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(slide, selected_layouts, color_scheme_data)

    agent = create_agent(
        model=_get_model(),
        tools=tools,
        system_prompt=system_prompt,
        middleware=[TokenCountingMiddleware(conv_id)],
    )

    # Increase recursion_limit — 25 is too low for multi-tool slide design loops
    agent_config = {**config, "recursion_limit": 50}
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config=agent_config,
    )

    # Retry if submit_slide_instruction wasn't called.
    # DeepSeek thinking mode doesn't support tool_choice, so we use a clean
    # text retry with a fresh agent that only has the submit tool — no
    # search_icons / read_instruction to distract it.
    if not was_called[0]:
        _log.warning("submit_slide_instruction not called for slide %d — retrying", slide_index)
        retry_agent = create_agent(
            model=_get_model(),
            tools=[submit_tool],
            system_prompt="你必须立即调用 submit_slide_instruction 提交当前 slide 的完整设计。直接提交，不要搜索或查阅任何资料。",
            middleware=[TokenCountingMiddleware(conv_id)],
        )
        await retry_agent.ainvoke(
            {"messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
                HumanMessage(content="请立即调用 submit_slide_instruction 提交当前 slide 的完整设计。不要再做任何搜索或浏览，直接提交。"),
            ]},
            config=config,
        )

    _log.info("SuperFreedomAgent done for slide %d (submitted=%s)", slide_index, was_called[0])
    return was_called[0]
