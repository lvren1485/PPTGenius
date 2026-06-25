"""Slide Agent — generates one slide's full visual design.  Pure memory, no DB.

Part-based model: submit_plan (define regions) → submit_background → submit_element
×N per part → check_parts (verify + complete).  Notes auto-generated from plan.
"""

from __future__ import annotations

import secrets

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pptgenius.infrastructure.ppt_engine.validator import validate_elements
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.middleware import build_middlewares
from ..common.sse_context import get_sse_writer
from pptgenius.infrastructure.llm import create_llm
from .common.tools import make_read_chart_instruction, make_read_instruction, make_search_icons
from .slide_prompts import build_system_prompt, build_user_prompt

_log = get_logger("pptgenius.agent.ppt.slide_agent")

_MAX_RETRIES = 3


async def run_slide_agent(
    conversation_id: int,
    slide: dict,
    style: dict | None,
    template: dict | None,
    query: str | None = None,
    *,
    existing_outputs: dict | None = None,
    pres_status: str | None = None,
    plan: dict | None = None,
) -> dict:
    """Generate one slide. Returns {slide_index, elements, notes, background, plan}.

    Pure memory — no DB access.  Each element gets an auto-generated hex id.

    If existing_outputs is provided (modify mode), the agent can see what
    elements already exist and decide what to keep/change/delete.
    """

    slide_index = slide.get("slide_index", 0)

    # ── memory buffer (closure-captured mutable dict) ──
    _buffer: dict = {
        "plan": plan,            # pre-populated from existing_outputs in modify mode
        "elements": {},          # {element_id: {..., "_part": "标题区"}}
        "background": {},        # slide background
    }

    # ── tools ──────────────────────────────────────────────────────────

    async def _submit_plan(
        design_concept: str,
        parts: list[dict],
    ) -> str:
        """Define or update the slide's part-based layout plan.

        First call creates the plan. Subsequent calls merge: matching part names
        update description + reset status to pending; new names are appended.
        Parts not listed in this call are preserved unchanged.

        Args:
            design_concept: 1-2 sentence visual concept. Leave empty to keep old value.
            parts: [{name, description}, ...] — regions to create or modify.
        """
        if not parts:
            return "错误: parts 不能为空。"

        plan = _buffer["plan"]
        if plan is None:
            plan = {"design_concept": "", "parts": {}}
            _buffer["plan"] = plan

        if design_concept:
            plan["design_concept"] = design_concept

        modified = []
        added = []
        for p in parts:
            name = p.get("name", "").strip()
            desc = p.get("description", "").strip()
            if not name or not desc:
                return f"错误: 每个 part 必须有 name 和 description。收到: name={name!r}"
            if name in plan["parts"]:
                plan["parts"][name]["description"] = desc
                plan["parts"][name]["status"] = "pending"
                modified.append(name)
            else:
                plan["parts"][name] = {"description": desc, "status": "pending"}
                added.append(name)

        msg_parts = []
        if added:
            msg_parts.append(f"新增 {len(added)} 个: {', '.join(added)}")
        if modified:
            msg_parts.append(f"修改 {len(modified)} 个: {', '.join(modified)}")
        return f"Plan 已更新 ({len(plan['parts'])} 个 part)。" + " ".join(msg_parts)

    async def _submit_element(
        element: dict | None = None,
        element_id: str = "",
        delete: bool = False,
        part: str = "",
    ) -> str:
        """Add, overwrite, or delete a slide element.

        ADD: omit element_id (or pass ""), provide element dict + part name.
        OVERWRITE: provide both element_id, element dict, and optional part.
        DELETE: provide element_id and set delete=true (element can be omitted).

        Args:
            element: The element dict (type, position, fill, etc). Omit for DELETE.
            element_id: 8-char hex id. Empty = new element. Non-empty = modify/delete existing.
            delete: Set to true to remove this element from the slide.
            part: Which plan part this element belongs to (e.g. "标题区").
        """
        if delete:
            if element_id and element_id in _buffer["elements"]:
                del _buffer["elements"][element_id]
                return f"已删除元素 {element_id}"
            return f"元素 {element_id} 不存在，无法删除"

        if not element:
            return "错误: 非删除操作必须提供 element。"

        # Attach part
        if part:
            element["_part"] = part

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

    async def _check_parts(part: str = "", complete: bool = False) -> str:
        """View part progress, element details, or mark a part complete.

        Args:
            part: Part name to inspect or complete. Empty = show all parts status.
            complete: Set true to mark the specified part as done.
        """
        plan = _buffer.get("plan")
        if plan is None:
            return "尚未提交 plan。请先调用 submit_plan。"

        if complete:
            if not part:
                return "错误: complete=true 但未指定 part 名称。"
            if part not in plan["parts"]:
                return f"Part '{part}' 不存在。可用: {', '.join(plan['parts'].keys())}"
            plan["parts"][part]["status"] = "complete"
            return f"Part '{part}' 已标记为完成。"

        if part:
            # View specific part
            if part not in plan["parts"]:
                return f"Part '{part}' 不存在。可用: {', '.join(plan['parts'].keys())}"
            info = plan["parts"][part]
            items = [
                f"**{part}** ({info['status']}): {info['description']}",
                "元素列表:",
            ]
            for eid, el in _buffer["elements"].items():
                if el.get("_part") == part:
                    items.append(
                        f"  - {eid}: type={el.get('type')}, "
                        f"shape_type={el.get('shape_type', '-')}"
                    )
            return "\n".join(items)

        # View all parts
        lines = [f"## Plan 进度 ({len(plan['parts'])} 个 part)", ""]
        for name, info in plan["parts"].items():
            count = sum(
                1 for el in _buffer["elements"].values()
                if el.get("_part") == name
            )
            lines.append(
                f"- **{name}**: [{info['status']}] {info['description'][:60]} "
                f"({count} 个元素)"
            )
        return "\n".join(lines)

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
        tool(_submit_plan),
        tool(_check_parts),
        tool(_submit_element),
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
                                    pres_status=pres_status,
                                    plan=plan)

    agent = create_agent(
        model=llm, tools=tools,
        system_prompt=system_prompt,
        middleware=mws,
    )

    try:
        writer = get_sse_writer()
        writer({"type": "slide_agent_start", "slide_index": slide_index})
    except RuntimeError:
        pass

    # ── main invoke + retry loop ───────────────────────────────────────

    from ..common.message_utils import prepare_retry_messages

    max_retries = _MAX_RETRIES
    messages = [HumanMessage(content=user_prompt)]
    result: dict | None = None

    for attempt in range(max_retries + 1):
        ag = agent if attempt == 0 else create_agent(
            model=llm, tools=tools,
            system_prompt=system_prompt,
            middleware=mws,
        )
        try:
            result = await ag.ainvoke(
                {"messages": messages},
                config={"recursion_limit": 100 if attempt == 0 else 50},
            )
        except Exception:
            _log.warning("slide_agent crashed slide=%d attempt=%d",
                        slide_index, attempt)
            _log.debug("slide_agent crash detail", exc_info=True)
            messages = prepare_retry_messages(result["messages"]) if result else messages
            continue

        # Check: empty submission (old retry condition)
        if not _buffer["elements"] and not _buffer["background"]:
            _log.warning("slide %d: no content submitted — retrying", slide_index)

        # Check: incomplete parts
        plan = _buffer.get("plan")
        incomplete = []
        if plan:
            incomplete = [
                name for name, info in plan["parts"].items()
                if info.get("status") != "complete"
            ]

        if not incomplete and _buffer["elements"]:
            break  # Done

        if attempt < max_retries:
            messages = prepare_retry_messages(result["messages"])
            if incomplete:
                pending = "\n".join(
                    f"  - {name}: {plan['parts'][name]['description'][:80]}"
                    for name in incomplete
                )
                msg = (
                    f"## 以下 part 尚未完成\n{pending}\n\n"
                    f"请继续调用 submit_element（指定 part 参数）填充这些区域的元素，"
                    f"完成后调用 check_parts(part='xxx', complete=True) 标记。"
                )
            else:
                msg = "请继续提交完整设计。调用 submit_background、submit_element（多次）。"
            messages.append(HumanMessage(content=msg))

    # ── build notes from plan ──────────────────────────────────────────

    plan = _buffer.get("plan")
    if plan:
        parts_lines = [
            f"[{name}] {info['description']}"
            for name, info in plan["parts"].items()
        ]
        notes = plan["design_concept"] + "\n\n" + "\n".join(parts_lines)
    else:
        notes = ""

    _log.info("slide %d done: %d elements, %d parts, bg=%s",
              slide_index, len(_buffer["elements"]),
              len(plan["parts"]) if plan else 0,
              _buffer["background"].get("type", "none"))

    return {
        "slide_index": slide_index,
        "elements": list(_buffer["elements"].values()),
        "notes": notes,
        "background": _buffer["background"],
        "plan": plan,
    }
