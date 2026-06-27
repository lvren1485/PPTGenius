"""Static tests for Phase 4 PPT agent — imports, prompt building, template loading.

Run: cd backend && uv run python -m pytest src/tests/test_phase4_static.py -v
"""

from __future__ import annotations

import json
import secrets


# ═══════════════════════════════════════════════════════════════════════
# 1. Import chain — all Phase 4 modules
# ═══════════════════════════════════════════════════════════════════════

def test_import_ppt_common():
    from pptgenius.agent.ppt.common import instruction_loader, tools
    assert instruction_loader is not None
    assert tools is not None


def test_import_instruction_loader():
    from pptgenius.agent.ppt.common.instruction_loader import (
        get_how_to_read,
        get_instruction,
        get_full_instruction_context,
        list_chart_instructions,
    )
    assert len(get_how_to_read()) > 0
    assert isinstance(get_instruction("background.json"), dict)
    assert len(get_full_instruction_context()) > 0
    assert len(list_chart_instructions()) >= 8


def test_import_ppt_tools():
    from pptgenius.agent.ppt.common.tools import (
        make_search_icons,
        make_read_instruction,
        make_read_chart_instruction,
    )
    from langchain_core.tools import BaseTool
    assert isinstance(make_search_icons(), BaseTool)
    assert isinstance(make_read_instruction(), BaseTool)
    assert isinstance(make_read_chart_instruction(), BaseTool)


def test_import_slide_prompts():
    from pptgenius.agent.ppt.slide_prompts import build_system_prompt, build_user_prompt
    sp = build_system_prompt()
    assert len(sp) > 5000
    # Second call hits @lru_cache
    sp2 = build_system_prompt()
    assert sp is sp2


def test_import_slide_agent():
    from pptgenius.agent.ppt.slide_agent import run_slide_agent
    import inspect
    sig = inspect.signature(run_slide_agent)
    params = list(sig.parameters.keys())
    assert "conversation_id" in params
    assert "existing_outputs" in params


def test_import_style_agent():
    from pptgenius.agent.ppt.style_agent import run_style_agent
    import inspect
    assert inspect.iscoroutinefunction(run_style_agent)


def test_import_tools():
    from pptgenius.agent.tools.ppt_style import make_ppt_style
    from pptgenius.agent.tools.slides_content import (
        make_slides_content,
        make_modify_slides_content,
        _write_slide_content,
        _LAYOUT_TYPE_MAP,
        _load_template_catalog,
    )
    assert callable(make_ppt_style)
    assert callable(make_slides_content)
    assert callable(make_modify_slides_content)
    assert isinstance(_LAYOUT_TYPE_MAP, dict)


def test_import_master():
    from pptgenius.agent.master import _TOOL_CTYPE, _SUB_AGENT_TOOLS
    assert "_ppt_style" in _TOOL_CTYPE
    assert "_slides_content" in _TOOL_CTYPE
    assert "_modify_slides_content" in _TOOL_CTYPE
    assert "ppt_style" in _SUB_AGENT_TOOLS
    assert "slides_content" in _SUB_AGENT_TOOLS
    assert "mod_slides" in _SUB_AGENT_TOOLS


# ═══════════════════════════════════════════════════════════════════════
# 2. Template catalog
# ═══════════════════════════════════════════════════════════════════════

def test_template_catalog_loaded():
    from pptgenius.agent.tools.slides_content import _load_template_catalog
    templates = _load_template_catalog()
    assert "title" in templates
    assert "section" in templates
    assert "content" in templates
    for key, tmpl in templates.items():
        assert "type" in tmpl
        assert "elements" in tmpl
        assert len(tmpl["elements"]) > 0


def test_layout_type_map_only_4_categories():
    from pptgenius.agent.tools.slides_content import _LAYOUT_TYPE_MAP
    categories = set(_LAYOUT_TYPE_MAP.values())
    assert categories == {"title", "section", "content"}
    # title + title_slide + thanks + ending → title
    assert _LAYOUT_TYPE_MAP["title"] == "title"
    assert _LAYOUT_TYPE_MAP["title_slide"] == "title"
    assert _LAYOUT_TYPE_MAP["ending"] == "title"
    assert _LAYOUT_TYPE_MAP["thanks"] == "title"
    assert _LAYOUT_TYPE_MAP["section"] == "section"
    assert _LAYOUT_TYPE_MAP["content"] == "content"


# ═══════════════════════════════════════════════════════════════════════
# 3. Prompt building
# ═══════════════════════════════════════════════════════════════════════

def test_user_prompt_content_full_no_truncation():
    from pptgenius.agent.ppt.slide_prompts import build_user_prompt
    long_text = "x" * 5000
    slide = {
        "slide_index": 1, "id": 1, "title": "测试",
        "layout_type": "content",
        "content_json": {"detailed_content": long_text, "main_points": ["a", "b"]},
    }
    style = {"label": "test", "name": "test", "colors": {"primary": "0000ff"}}
    template = {"type": "content", "name": "content"}
    user = build_user_prompt(slide, style, template)
    assert long_text in user  # NOT truncated


def test_user_prompt_background_full_json():
    from pptgenius.agent.ppt.slide_prompts import build_user_prompt
    slide = {
        "slide_index": 1, "title": "测试", "layout_type": "content",
        "content_json": {"main_points": ["a"]},
    }
    style = {
        "label": "test", "name": "test",
        "colors": {"primary": "0000ff", "accent": "ff0000"},
        "background_json": {
            "type": "gradient", "gradient_angle": 135,
            "gradient_stops": [
                {"position": 0, "color": "1a237e"},
                {"position": 1, "color": "3949ab"},
            ],
        },
    }
    template = {"type": "content"}
    user = build_user_prompt(slide, style, template)
    assert "gradient_angle" in user
    assert "gradient_stops" in user
    assert "1a237e" in user


def test_user_prompt_existing_outputs_raw_json():
    from pptgenius.agent.ppt.slide_prompts import build_user_prompt
    slide = {
        "slide_index": 1, "title": "测试", "layout_type": "content",
        "content_json": {"main_points": ["a"]},
    }
    style = {"label": "test", "name": "test", "colors": {}}
    template = {"type": "content"}
    eo = {
        "elements": [
            {"id": "abc12345", "type": "shape", "shape_type": "rectangle",
             "position": {"left": 1, "top": 2, "width": 3, "height": 4},
             "fill": {"type": "solid", "color": "ff0000"}}
        ],
        "background": {"type": "gradient", "gradient_angle": 90},
        "notes": "design rationale: used gradient for tech atmosphere",
    }
    user = build_user_prompt(slide, style, template, existing_outputs=eo)
    assert "abc12345" in user                             # element id
    assert "修改模式" in user                              # modify mode label
    assert "gradient" in user                             # background type summary


def test_build_user_prompt_caches_are_independent():
    from pptgenius.agent.ppt.slide_prompts import build_system_prompt, build_user_prompt
    sp1 = build_system_prompt()
    sp2 = build_system_prompt()
    assert sp1 is sp2  # lru_cache hit
    slide = {"slide_index": 1, "title": "A", "layout_type": "content", "content_json": {"main_points": ["a"]}}
    style = {"label": "t", "name": "t", "colors": {}}
    u1 = build_user_prompt(slide, style, {"type": "content"})
    u2 = build_user_prompt(slide, style, {"type": "content"})
    assert u1 == u2  # same inputs, same output
    assert u1 is not u2  # not cached (different calls)


# ═══════════════════════════════════════════════════════════════════════
# 4. Color scheme background_json
# ═══════════════════════════════════════════════════════════════════════

def test_color_schemes_have_background_json():
    from pptgenius.infrastructure.config import RESOURCES_DIR
    cs_dir = RESOURCES_DIR / "color_schemes"
    for f in sorted(cs_dir.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        assert "background_json" in d, f"{f.name} missing background_json"
        bg = d["background_json"]
        assert "type" in bg
        assert bg["type"] in ("solid", "gradient")
        assert "color" in bg


# ═══════════════════════════════════════════════════════════════════════
# 5. Instruction loader caches
# ═══════════════════════════════════════════════════════════════════════

def test_instruction_loader_cache():
    from pptgenius.agent.ppt.common.instruction_loader import get_instruction, get_how_to_read
    h1 = get_how_to_read()
    h2 = get_how_to_read()
    assert h1 is h2  # lru_cache hit
    i1 = get_instruction("textbox.json")
    i2 = get_instruction("textbox.json")
    assert i1 is i2  # lru_cache hit


# ═══════════════════════════════════════════════════════════════════════
# 7. search_styles in perception
# ═══════════════════════════════════════════════════════════════════════

def test_make_search_styles_exists():
    from pptgenius.agent.tools.perception import make_search_styles
    assert callable(make_search_styles)
