"""Slide Agent — generates one slide's full visual design.  Pure memory, no DB.

Three-tool model: submit_element (add/overwrite/delete), submit_notes (append),
submit_background (set).  Returns a result dict — caller writes to DB.
"""

from __future__ import annotations

import secrets

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.ppt_engine.validator import validate_elements
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.middleware import build_middlewares
from pptgenius.infrastructure.llm import create_llm
from .common.tools import make_read_chart_instruction, make_read_instruction, make_search_icons
from .slide_prompts import build_system_prompt, build_user_prompt

_log = get_logger("pptgenius.agent.ppt.slide_agent")


async def run_slide_agent(
    conversation_id: int,
    slide: dict,
    style: dict | None,
    template: dict | None,
    query: str | None = None,
    *,
    existing_outputs: dict | None = None,
    pres_status: str | None = None,
) -> dict:
    """Generate one slide. Returns {slide_index, elements, notes, background}.

    Pure memory — no DB access.  Each element gets an auto-generated hex id.

    If existing_outputs is provided (modify mode), the agent can see what
    elements already exist and decide what to keep/change/delete.
    """

    slide_index = slide.get("slide_index", 0)

    # ── memory buffer (closure-captured mutable dict) ──
    _buffer: dict = {
        "elements": {},   # {element_id: element_dict}
        "notes": "",       # speaker notes (append-only)
        "background": {},  # slide background
    }

    # ── tools ──────────────────────────────────────────────────────────

    async def _submit_element(
        element: dict | None = None,
        element_id: str = "",
        delete: bool = False,
    ) -> str:
        """Add, overwrite, or delete a slide element.

        ADD: omit element_id (or pass ""), provide element dict.
        OVERWRITE: provide both element_id and element dict.
        DELETE: provide element_id and set delete=true (element can be omitted).

        Args:
            element: The element dict (type, position, fill, etc). Omit for DELETE.
            element_id: 8-char hex id. Empty = new element. Non-empty = modify/delete existing.
            delete: Set to true to remove this element from the slide.
        """
        if delete:
            if element_id and element_id in _buffer["elements"]:
                del _buffer["elements"][element_id]
                return f"已删除元素 {element_id}"
            return f"元素 {element_id} 不存在，无法删除"

        if not element:
            return "错误: 非删除操作必须提供 element。"

        # Validate
        result = validate_elements([element])
        if not result.is_valid:
            errors = "\n".join(
                f"  - [{e['path']}] {e['error']}" for e in result.errors[:10]
            )
            return (
                f"校验失败 ({len(result.errors)} 个错误):\n{errors}\n"
                f"请根据错误修正后重新提交。"
            )

        if element_id and element_id in _buffer["elements"]:
            _buffer["elements"][element_id] = element
            return f"已覆盖元素 {element_id} (type={element.get('type')})"
        else:
            eid = element_id or secrets.token_hex(4)
            _buffer["elements"][eid] = element
            return f"已添加元素 {eid} (type={element.get('type')})"

    async def _submit_notes(notes: str) -> str:
        """Append speaker notes for this slide.  Call multiple times to accumulate.

        Args:
            notes: The speaker notes text to append.
        """
        if _buffer["notes"]:
            _buffer["notes"] += "\n\n" + notes
        else:
            _buffer["notes"] = notes
        return f"已追加 notes ({len(notes)} chars, 总计 {len(_buffer['notes'])} chars)"

    async def _submit_background(background: dict) -> str:
        """Set the slide background. Overwrites any previous setting.

        Args:
            background: Background dict, e.g. {"type":"solid","color":"F8FAFC"}
                or {"type":"gradient","gradient_angle":135,"gradient_stops":[...]}.
        """
        bg_type = background.get("type", "")
        if bg_type not in ("solid", "gradient", "image", "no_fill"):
            return f"background.type 无效: '{bg_type}'。有效值: solid, gradient, image, no_fill"
        if bg_type == "gradient" and not background.get("gradient_stops"):
            return "gradient 背景必须包含 gradient_stops。"
        _buffer["background"] = background
        return f"已设置背景 (type={bg_type})"

    tools = [
        tool(_submit_element),
        tool(_submit_notes),
        tool(_submit_background),
        make_search_icons(),
        make_read_instruction(),
        make_read_chart_instruction(),
    ]

    # ── build agent ───────────────────────────────────────────────────

    llm, agent_id = create_llm(conversation_id)
    mws, _ = build_middlewares(conversation_id, agent_id)
    push_agent(conversation_id, agent_id)

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(slide, style, template, query,
                                    existing_outputs=existing_outputs,
                                    pres_status=pres_status)

    agent = create_agent(
        model=llm, tools=tools,
        system_prompt=system_prompt,
        middleware=mws,
    )

    try:
        writer = get_stream_writer()
        writer({"type": "slide_agent_start", "slide_index": slide_index})
    except RuntimeError:
        pass

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config={"recursion_limit": 100},
    )

    # ── retry if no elements submitted ────────────────────────────────

    if not _buffer["elements"] and not _buffer["background"]:
        _log.warning("slide %d: no content submitted — retrying with submit-only agent", slide_index)
        submit_tools = [tool(_submit_element), tool(_submit_notes), tool(_submit_background)]
        retry_agent = create_agent(
            model=llm, tools=submit_tools,
            system_prompt="你必须立即提交 slide 的完整设计。直接调用 submit_background、submit_element 和 submit_notes。不要再搜索或查阅任何资料。",
            middleware=mws,
        )
        await retry_agent.ainvoke(
            {"messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
                HumanMessage(content="请立即提交完整设计。调用 submit_background、submit_element（多次）、submit_notes。"),
            ]},
            config={"recursion_limit": 30},
        )

    _log.info("slide %d done: %d elements, notes=%d chars, bg=%s",
              slide_index, len(_buffer["elements"]),
              len(_buffer["notes"]), _buffer["background"].get("type", "none"))

    return {
        "slide_index": slide_index,
        "elements": list(_buffer["elements"].values()),
        "notes": _buffer["notes"],
        "background": _buffer["background"],
    }
