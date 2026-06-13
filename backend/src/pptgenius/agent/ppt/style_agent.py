"""Style Agent — selects a color/layout style for a presentation.

Based on agent_old/ppt/phase1_style.py, adapted to the new build_llm() framework.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.config import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.model_builder import build_llm

_log = get_logger("pptgenius.agent.ppt.style_agent")

_PROMPT_PATH = RESOURCES_DIR / "prompts" / "ppt" / "style_agent_system.txt"
_LAYOUTS_DIR = RESOURCES_DIR / "layouts"


def _load_system_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a PPT style designer. Select color schemes and layouts."


async def run_style_agent(
    db: Database,
    conversation_id: int,
) -> dict:
    """Select a style for the current outline's presentation.

    Returns {style_id, style_name, style_label, rationale}.
    Creates the presentation if it doesn't exist yet.
    """

    conv = await db.get_conversation(conversation_id)
    if conv is None or conv.current_outline_id is None:
        return {"error": "没有选中大纲"}

    outline_id = conv.current_outline_id
    outline = await db.get_outline(outline_id)

    # Ensure presentation exists
    pres_list = await db.list_presentations_by_conversation(conversation_id)
    pres = next((p for p in pres_list if p.outline_id == outline_id and p.status != "deleted"), None)
    if pres is None:
        pres = await db.create_presentation(
            user_id=conv.user_id,
            conversation_id=conversation_id,
            outline_id=outline_id,
        )
    presentation_id = pres.id

    # ── mutable result containers ──
    _style_id: list[int | None] = [None]
    _rationale: list[str] = [""]
    _was_called: list[bool] = [False]

    # ── tools ────────────────────────────────────────────────────────

    async def _list_styles(dummy: str = "") -> str:
        """List all active styles in the database. Pass empty string."""
        styles = await db.search_styles("")
        if not styles:
            return "数据库中没有可用样式。使用 save_style 创建一个。"
        items = []
        for s in styles:
            items.append(json.dumps({
                "id": s.id, "name": s.name, "label": s.label,
                "style_density": s.style_density,
                "colors": s.colors_json,
                "background": s.background_json,
            }, ensure_ascii=False))
        return "\n\n".join(items)

    async def _get_style(style_id: int) -> str:
        """Get full details of a style by ID.

        Args:
            style_id: The style ID from list_styles.
        """
        s = await db.get_style(style_id)
        if s is None:
            return f"样式 id={style_id} 不存在。"
        return json.dumps({
            "id": s.id, "name": s.name, "label": s.label,
            "style_density": s.style_density,
            "colors": s.colors_json,
            "chart_colors": s.chart_colors_json,
            "fonts": s.fonts_json,
            "decoration": s.decoration_json,
            "background": s.background_json,
        }, ensure_ascii=False, indent=2)

    async def _save_style(
        name: str,
        label: str,
        colors: dict,
        chart_colors: list[str],
        fonts: dict,
        style_density: str = "moderate",
        decoration: dict | None = None,
        background: dict | None = None,
    ) -> str:
        """Create a new style.

        Args:
            name: Unique identifier, e.g. 'tech_green'.
            label: Display name, e.g. '科技绿'.
            colors: {primary, accent, text, text_secondary, bg, bg_dark, border}.
                Hex without '#' prefix.
            chart_colors: 4-6 hex colors for charts.
            fonts: {h1, h2, h3, h4, body, caption, min_size}.
            style_density: 'minimal' | 'moderate' | 'elaborate'.
            decoration: Decoration toggles dict.
            background: Background preset, e.g. {"type":"solid","color":"f8f9fa"}.
        """
        valid = {"minimal", "moderate", "elaborate"}
        if style_density not in valid:
            return f"style_density 必须为 {valid} 之一"

        try:
            s = await db.create_style(
                name=name, label=label,
                colors_json=colors,
                chart_colors_json=chart_colors,
                fonts_json=fonts,
                style_density=style_density,
                decoration_json=decoration or {},
                background_json=background,
            )
            return json.dumps({
                "id": s.id, "name": s.name, "label": s.label,
                "message": f"样式 '{label}' 创建成功 (id={s.id})。",
            }, ensure_ascii=False)
        except Exception as exc:
            return f"创建失败: {exc}。name 可能已存在。"

    async def _list_layouts(dummy: str = "") -> str:
        """List all built-in layout templates. Pass empty string."""
        items = []
        for f in sorted(_LAYOUTS_DIR.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                items.append(f"- **{d['name']}**: {d['label']}")
            except Exception:
                items.append(f"- {f.stem}")
        return "\n".join(items) if items else "没有找到布局模板。"

    async def _get_layout(name: str) -> str:
        """Get full layout definition by name.

        Args:
            name: Layout name, e.g. 'title_slide', 'content_two_column'.
        """
        path = _LAYOUTS_DIR / f"{name}.json"
        if not path.exists():
            available = [f.stem for f in sorted(_LAYOUTS_DIR.glob("*.json"))]
            return f"布局 '{name}' 不存在。可用: {', '.join(available)}"
        return path.read_text(encoding="utf-8")

    async def _set_presentation_style(
        style_id: int,
        design_rationale: str,
    ) -> str:
        """Commit the style selection to the presentation. MUST be called last.

        Args:
            style_id: The selected style ID.
            design_rationale: Why you chose this style.
        """
        await db.set_presentation_style(presentation_id, style_id=style_id)
        _style_id[0] = style_id
        _rationale[0] = design_rationale
        _was_called[0] = True
        _log.info("style selected for pres=%d: style=%d", presentation_id, style_id)
        return json.dumps({"status": "ok", "style_id": style_id}, ensure_ascii=False)

    tools = [
        tool(_list_styles),
        tool(_get_style),
        tool(_save_style),
        tool(_list_layouts),
        tool(_get_layout),
        tool(_set_presentation_style),
    ]

    # ── build agent ──────────────────────────────────────────────────

    llm, agent_id, mw = build_llm(conversation_id)
    push_agent(conversation_id, agent_id)

    slides = await db.get_slides_by_outline_id(outline_id)
    lt_summary = {}
    for s in slides:
        lt = s.layout_type or "content"
        lt_summary[lt] = lt_summary.get(lt, 0) + 1

    user_prompt = (
        f"## 大纲信息\n"
        f"标题: {outline.title if outline else '未命名'}\n"
        f"页数: {len(slides)}\n"
        f"页面类型分布: {json.dumps(lt_summary, ensure_ascii=False)}\n\n"
        f"请按照工作流程选择配色方案和布局模板。"
    )

    agent = create_agent(
        model=llm, tools=tools,
        system_prompt=_load_system_prompt(),
        middleware=[mw],
    )

    try:
        writer = get_stream_writer()
        writer({"type": "style_agent_start"})
    except RuntimeError:
        pass

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config={"recursion_limit": 30},
    )

    # Retry if set_presentation_style wasn't called
    if not _was_called[0]:
        _log.warning("set_presentation_style not called — retrying")
        retry_agent = create_agent(
            model=llm,
            tools=[tool(_set_presentation_style)],
            system_prompt="你必须立即调用 set_presentation_style 提交风格选择。直接选择最合适的样式并提交。",
            middleware=[mw],
        )
        await retry_agent.ainvoke(
            {"messages": [
                HumanMessage(content=user_prompt),
                HumanMessage(content="请立即调用 set_presentation_style 提交。不要再浏览或搜索。"),
            ]},
            config={"recursion_limit": 10},
        )
        _was_called[0] = True

    style_id = _style_id[0]
    if style_id:
        s = await db.get_style(style_id)
        label = s.label if s else ""
    else:
        label = ""

    return {
        "style_id": style_id,
        "style_label": label,
        "rationale": _rationale[0],
    }
