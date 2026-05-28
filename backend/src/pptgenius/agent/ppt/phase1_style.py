"""Phase 1 StyleAgent — selects color_scheme and layout template.

Uses create_agent with 6 tools:
  list_color_schemes, get_color_scheme, save_color_scheme,
  list_layouts, get_layout, set_presentation_style (terminal).

The agent browses available color schemes, optionally creates a new one,
then MUST call set_presentation_style to persist the selection.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.agent.outline.middleware import TokenCountingMiddleware
from pptgenius.infrastructure.config import RESOURCES_DIR, get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

from .state import PPTState

_log = get_logger("pptgenius.agent.ppt.phase1_style")

apply_deepseek_patch()

_PROMPT_PATH = RESOURCES_DIR / "prompts" / "ppt" / "style_agent_system.txt"
_LAYOUTS_DIR = RESOURCES_DIR / "layouts"


def _get_model() -> ChatOpenAI:
    cfg = get_settings().llm
    return ChatOpenAI(
        model=cfg.model,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        temperature=0.3,
        max_tokens=8000,
    )


def _load_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a PPT style designer. Select color schemes and layouts."


# ── tools ─────────────────────────────────────────────────────────────────────


def _make_list_color_schemes(db: Database):
    @tool
    async def list_color_schemes(dummy: str = "") -> str:
        """List all active color schemes in the database.

        Pass an empty string as the argument.
        """
        schemes = await db.list_active_color_schemes()
        if not schemes:
            return "数据库中没有可用的配色方案。使用 save_color_scheme 创建一个。"

        items = []
        for cs in schemes:
            items.append(json.dumps({
                "id": cs.id,
                "name": cs.name,
                "label": cs.label,
                "style_density": getattr(cs, "style_density", "moderate"),
                "decoration": getattr(cs, "decoration_json", {}),
                "colors": cs.colors_json,
            }, ensure_ascii=False))
        return "\n\n".join(items)

    return list_color_schemes


def _make_get_color_scheme(db: Database):
    @tool
    async def get_color_scheme(scheme_id: int) -> str:
        """Get the full definition of a single color scheme by ID.

        Parameters
        ----------
        scheme_id : int — The color scheme ID from list_color_schemes.
        """
        cs = await db.get_color_scheme(scheme_id)
        if cs is None:
            return f"配色方案 id={scheme_id} 不存在。"
        return json.dumps({
            "id": cs.id,
            "name": cs.name,
            "label": cs.label,
            "style_density": getattr(cs, "style_density", "moderate"),
            "decoration": getattr(cs, "decoration_json", {}),
            "colors": cs.colors_json,
            "chart_colors": cs.chart_colors_json,
            "fonts": cs.fonts_json,
        }, ensure_ascii=False, indent=2)

    return get_color_scheme


def _make_save_color_scheme(db: Database):
    @tool
    async def save_color_scheme(
        name: str,
        label: str,
        colors: dict,
        chart_colors: list[str],
        fonts: dict,
        style_density: str = "moderate",
        decoration: dict | None = None,
    ) -> str:
        """Create a new color scheme in the database.

        Parameters
        ----------
        name : str — Unique identifier, e.g. 'tech_green'
        label : str — Display name, e.g. '科技绿'
        colors : dict — {primary, accent, text, text_secondary, bg, bg_dark, border}
            All values are 6-char hex strings WITHOUT '#' prefix.
        chart_colors : list[str] — 4-6 hex colors for chart series.
        fonts : dict — {title, subtitle, body, caption}, each with {name, size, bold, color}.
        style_density : str — 'minimal' | 'moderate' | 'elaborate'. Default 'moderate'.
        decoration : dict — Decoration toggles. Default {}.
        """
        valid_density = {"minimal", "moderate", "elaborate"}
        if style_density not in valid_density:
            return f"style_density 必须为 {valid_density} 之一，当前值为 '{style_density}'。"

        try:
            cs = await db.create_color_scheme(
                name=name,
                label=label,
                colors_json=colors,
                chart_colors_json=chart_colors,
                fonts_json=fonts,
                style_density=style_density,
                decoration_json=decoration or {},
            )
            return json.dumps({
                "id": cs.id,
                "name": cs.name,
                "label": cs.label,
                "message": f"配色方案 '{label}' 创建成功 (id={cs.id})。",
            }, ensure_ascii=False)
        except Exception as exc:
            return f"创建失败: {exc}。请检查 name 是否已存在。"

    return save_color_scheme


def _make_list_layouts():
    @tool
    async def list_layouts(dummy: str = "") -> str:
        """List all built-in layout templates.

        Pass an empty string as the argument.
        """
        items = []
        for f in sorted(_LAYOUTS_DIR.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                items.append(f"- **{d['name']}**: {d['label']}")
            except Exception:
                items.append(f"- {f.stem}")
        if not items:
            return "没有找到布局模板文件。"
        return "\n".join(items)

    return list_layouts


def _make_get_layout():
    @tool
    async def get_layout(name: str) -> str:
        """Get the full definition of a layout by name.

        Parameters
        ----------
        name : str — Layout name, e.g. 'title_slide', 'content_two_column'.
        """
        path = _LAYOUTS_DIR / f"{name}.json"
        if not path.exists():
            available = [f.stem for f in sorted(_LAYOUTS_DIR.glob("*.json"))]
            return f"布局 '{name}' 不存在。可用: {', '.join(available)}"
        return path.read_text(encoding="utf-8")

    return get_layout


def _make_set_presentation_style(db: Database, presentation_id: int):
    """Returns (tool, get_ids).  Use mutable wrappers to capture selections."""
    _cs_id: list[int | None] = [None]
    _layouts: list[dict] = [{}]
    _rationale: list[str] = [""]
    _called: list[bool] = [False]

    @tool
    async def set_presentation_style(
        color_scheme_id: int,
        design_rationale: str,
    ) -> str:
        """Write the final style selection to the presentation record.
        This MUST be called as the last action.

        Parameters
        ----------
        color_scheme_id : int — The selected color scheme ID.
        design_rationale : str — Why you chose this scheme and style.
        """
        # Update presentation record
        await db.update_presentation_status(presentation_id, "slides_generating")
        _log.info(
            "Style selected for presentation %d: cs=%d rationale=%s",
            presentation_id, color_scheme_id, design_rationale[:80],
        )

        _cs_id[0] = color_scheme_id
        _rationale[0] = design_rationale
        _called[0] = True

        return json.dumps({
            "status": "ok",
            "presentation_id": presentation_id,
            "color_scheme_id": color_scheme_id,
            "design_rationale": design_rationale,
        }, ensure_ascii=False)

    def _get_result() -> tuple[int | None, str, bool]:
        return _cs_id[0], _rationale[0], _called[0]

    return set_presentation_style, _get_result


# ── style agent node ──────────────────────────────────────────────────────────


async def style_agent_node(state: PPTState, config: RunnableConfig) -> dict:
    """Phase 1: StyleAgent selects color_scheme and confirms layout template."""
    db: Database = config["configurable"]["db"]
    conv_id = state["conversation_id"]
    presentation_id = state["presentation_id"]

    if presentation_id is None:
        _log.error("style_agent called without presentation_id")
        return {}

    try:
        writer = get_stream_writer()
    except RuntimeError:
        writer = lambda _: None

    set_style_tool, get_result = _make_set_presentation_style(db, presentation_id)

    tools = [
        _make_list_color_schemes(db),
        _make_get_color_scheme(db),
        _make_save_color_scheme(db),
        _make_list_layouts(),
        _make_get_layout(),
        set_style_tool,
    ]

    system_prompt = _load_prompt()

    # Load outline info for context
    outline = await db.get_outline(state["outline_id"])
    outline_title = outline.title if outline else "未命名"
    slides = state.get("outline_slides", [])
    lt_summary = {}
    for s in slides:
        lt = s.get("layout_type", "content")
        lt_summary[lt] = lt_summary.get(lt, 0) + 1

    user_prompt = (
        f"## 大纲信息\n"
        f"标题: {outline_title}\n"
        f"页数: {len(slides)}\n"
        f"页面类型分布: {json.dumps(lt_summary, ensure_ascii=False)}\n\n"
        f"请按照工作流程选择配色方案和布局模板。"
    )

    agent = create_agent(
        model=_get_model(),
        tools=tools,
        system_prompt=system_prompt,
        middleware=[TokenCountingMiddleware(conv_id)],
    )

    writer({"type": "style_agent_start"})
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config=config,
    )
    writer({"type": "style_agent_end"})

    cs_id, rationale, was_called = get_result()

    # Retry if set_presentation_style wasn't called
    if not was_called:
        _log.warning("set_presentation_style not called — retrying")
        retry_msg = HumanMessage(
            content="请立即调用 set_presentation_style 工具提交你的风格选择。"
            "不要再浏览或搜索，直接选择最合适的配色方案并提交。"
        )
        result2 = await agent.ainvoke(
            {"messages": list(result["messages"]) + [retry_msg]},
            config=config,
        )
        cs_id, rationale, was_called = get_result()
        result = result2

    return {
        "color_scheme_id": cs_id,
        "template_id": 1,  # default template
        "style_rationale": rationale,
        "messages": result["messages"],
    }
