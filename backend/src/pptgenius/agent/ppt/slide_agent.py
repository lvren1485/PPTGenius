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

from .spatial_check import check_element as _check_spatial
from .spatial_check import check_plan_bounds as _check_plan_bounds
from .decor_check import check_decor as _check_decor_style


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
            parts: [{name, description, bounds?, has_chart?, has_table?, has_image?}, ...]
                Each part has required name+description and optional spatial/type metadata:
                - bounds: {left, top, width, height} — estimated region (inches)
                - has_chart: bool — part will contain a chart (needs ≥2×2")
                - has_table: bool — part will contain a table (needs ≥3×1.5")
                - has_image: bool — part will contain an image (needs ≥0.5×0.5")
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
                entry = plan["parts"][name]
                entry["description"] = desc
                entry["status"] = "pending"
                for k in ("bounds", "has_chart", "has_table", "has_image", "decor_style"):
                    if k in p:
                        entry[k] = p[k]
                modified.append(name)
            else:
                entry = {"description": desc, "status": "pending"}
                for k in ("bounds", "has_chart", "has_table", "has_image", "decor_style"):
                    if k in p:
                        entry[k] = p[k]
                plan["parts"][name] = entry
                added.append(name)

        msg_parts = []
        if added:
            msg_parts.append(f"新增 {len(added)} 个: {', '.join(added)}")
        if modified:
            msg_parts.append(f"修改 {len(modified)} 个: {', '.join(modified)}")

        # C1/C2: bounds-aware spatial pre-check
        pw = _check_plan_bounds(plan["parts"])
        result = f"Plan 已更新 ({len(plan['parts'])} 个 part)。" + " ".join(msg_parts)
        if pw:
            result += "\n⚠ 空间规划:\n" + "\n".join(f"  - {w}" for w in pw)
        return result

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

        # Decor style enforcement (emoji vs icon)
        decor_note = _check_decor_style(element, _buffer, part)
        if decor_note:
            return decor_note  # hard reject — conflicting decor style

        # Spatial check (warning only, never blocks)
        spatial_note = _check_spatial(element, _buffer)

        if element_id and element_id in _buffer["elements"]:
            _buffer["elements"][element_id] = element
            msg = f"已覆盖元素 {element_id} (type={element.get('type')})"
        else:
            eid = element_id or secrets.token_hex(4)
            _buffer["elements"][eid] = element
            msg = f"已添加元素 {eid} (type={element.get('type')})"

        if spatial_note:
            msg += "\n" + spatial_note
        return msg

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

    max_retries = _MAX_RETRIES
    messages = [HumanMessage(content=user_prompt)]
    result: dict | None = None

    for attempt in range(max_retries + 1):
        crashed = False
        # Always fresh agent — avoids any stale state from prior attempts
        ag = create_agent(
            model=llm, tools=tools,
            system_prompt=system_prompt,
            middleware=mws,
        )
        try:
            result = await ag.ainvoke(
                {"messages": messages},
                config={"recursion_limit": 200},
            )
        except Exception:
            _log.warning("slide_agent crashed slide=%d attempt=%d",
                        slide_index, attempt)
            _log.debug("slide_agent crash detail", exc_info=True)
            crashed = True

        # Check completion
        current_plan = _buffer.get("plan")
        incomplete: list[str] = []
        if current_plan:
            incomplete = [
                name for name, info in current_plan["parts"].items()
                if info.get("status") != "complete"
            ]
        has_content = bool(_buffer["elements"]) or bool(_buffer["background"])

        if not incomplete and has_content:
            break

        if attempt >= max_retries:
            break

        # ── retry: fresh conversation + state-aware prompt ─────────────

        if crashed:
            # Reset buffer — partial state from crashed run is unreliable
            _buffer["plan"] = plan           # original from args (modify mode)
            _buffer["elements"] = {}
            _buffer["background"] = {}

        cur = _buffer.get("plan")
        num_el = len(_buffer["elements"])
        bg_type = _buffer["background"].get("type", "") if _buffer["background"] else ""

        if not crashed and cur and has_content:
            # Valid buffer — tell LLM to inspect and continue
            inc_names = [n for n, i in cur["parts"].items() if i.get("status") != "complete"]
            retry_msg = (
                f"## 重试 — 当前进度\n"
                f"已有 plan（{len(cur['parts'])} 个 part）、{num_el} 个元素、"
                f"背景类型={bg_type or '未设置'}。\n"
                f"请先调用 check_parts() 查看状态，然后继续完成以下未完成的 part:\n"
            )
            for name in inc_names:
                retry_msg += f"  - {name}: {cur['parts'][name]['description'][:80]}\n"
            retry_msg += (
                f"\n重要：不要重新调用 submit_plan（plan 已存在，重新调用会重置 part 状态）。"
                f"直接调用 check_parts() 查看后，继续 submit_element 填充。"
            )
        else:
            # Buffer reset or no plan — start fresh
            retry_msg = (
                f"## 重试\n"
                f"上次调用失败，请重新开始设计。"
                f"按步骤：submit_plan → submit_background → submit_element ×N → check_parts 标记完成。"
            )

        messages = [HumanMessage(content=user_prompt), HumanMessage(content=retry_msg)]

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
