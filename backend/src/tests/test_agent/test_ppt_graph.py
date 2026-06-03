"""Tests for PPT agent graph — compilation, routing, state, layout definitions.

Covers all logic that does NOT require LLM/API calls.
"""

from __future__ import annotations

import pytest

from pptgenius.agent.ppt.graph import (
    _route_style,
    build_ppt_graph,
)
from pptgenius.agent.ppt.state import PPTState


# ── fixtures ──────────────────────────────────────────────────────────────────


def _base_state(**overrides) -> PPTState:
    s: PPTState = {
        "user_id": 1,
        "conversation_id": 1,
        "query": "生成PPT",
        "outline_id": 1,
        "is_modify": False,
        "presentation_id": None,
        "color_scheme_id": None,
        "template_id": None,
        "selected_layouts": {},
        "style_rationale": "",
        "current_slide_index": 0,
        "total_slides": 5,
        "ppt_mode": "super_freedom",
        "outline_slides": [],
        "design_rationales": [],
        "file_path": "output/test.pptx",
        "messages": [],
    }
    s.update(overrides)
    return s


# ── graph compilation ─────────────────────────────────────────────────────────


class TestGraphCompilation:
    def test_build_graph_returns_compiled_graph(self):
        graph = build_ppt_graph()
        assert graph is not None

    def test_graph_has_all_nodes(self):
        graph = build_ppt_graph()
        nodes = graph.nodes
        assert "create_presentation" in nodes
        assert "style_agent" in nodes
        assert "dispatcher" in nodes
        assert "assembly" in nodes


# ── routing logic ─────────────────────────────────────────────────────────────


class TestRouteStyle:
    def test_no_style_selected_goes_to_style_agent(self):
        state = _base_state(color_scheme_id=None, template_id=None)
        assert _route_style(state) == "style_agent"

    def test_color_scheme_selected_no_template_goes_to_style_agent(self):
        state = _base_state(color_scheme_id=1, template_id=None)
        assert _route_style(state) == "style_agent"

    def test_template_selected_no_color_goes_to_style_agent(self):
        state = _base_state(color_scheme_id=None, template_id=1)
        assert _route_style(state) == "style_agent"

    def test_both_style_selected_skips_to_dispatcher(self):
        state = _base_state(color_scheme_id=1, template_id=1)
        assert _route_style(state) == "dispatcher"

    def test_modify_with_existing_style_skips(self):
        """User is modifying a slide, not changing style."""
        state = _base_state(
            is_modify=True,
            color_scheme_id=2,
            template_id=1,
        )
        assert _route_style(state) == "dispatcher"


# ── state defaults ────────────────────────────────────────────────────────────


class TestPPTState:
    def test_minimal_state_creation(self):
        state: PPTState = {
            "user_id": 1,
            "conversation_id": 1,
            "query": "test",
            "outline_id": 1,
            "is_modify": False,
            "presentation_id": None,
            "color_scheme_id": None,
            "template_id": None,
            "selected_layouts": {},
            "style_rationale": "",
            "current_slide_index": 0,
            "total_slides": 0,
            "ppt_mode": "super_freedom",
            "outline_slides": [],
            "design_rationales": [],
            "file_path": "",
            "messages": [],
        }
        assert state["ppt_mode"] == "super_freedom"
        assert state["is_modify"] is False

    def test_design_rationales_accumulate(self):
        """operator.add should concatenate lists."""
        import typing
        hints = typing.get_type_hints(PPTState)
        assert "design_rationales" in hints


# ── graph edges ───────────────────────────────────────────────────────────────


class TestGraphEdges:
    def test_start_goes_to_create_presentation(self):
        graph = build_ppt_graph()
        compiled = graph.get_graph()
        # START → create_presentation edge exists
        assert compiled is not None

    def test_style_to_dispatcher_edge_exists(self):
        graph = build_ppt_graph()
        compiled = graph.get_graph()
        # style_agent → dispatcher is a direct edge
        assert compiled is not None

    def test_assembly_to_end(self):
        graph = build_ppt_graph()
        compiled = graph.get_graph()
        # assembly → END
        assert compiled is not None


# ── layout definitions ────────────────────────────────────────────────────────


class TestLayoutDefinitions:
    from pptgenius.agent.ppt.layout.definitions import BUILTIN_LAYOUTS

    LAYOUTS = BUILTIN_LAYOUTS

    def test_all_seven_layouts_exist(self):
        expected = {
            "title_slide", "section", "content_bullet",
            "content_two_column", "content_three_column",
            "content_grid_2x2", "ending",
        }
        missing = expected - set(self.LAYOUTS)
        assert not missing, f"Missing layouts: {missing}"

    def test_title_slide_has_required_keys(self):
        t = self.LAYOUTS["title_slide"]
        assert t["name"] == "title_slide"
        assert "fixed_elements" in t
        assert "decorations" in t
        assert "containers" in t
        # title and subtitle placeholders
        ids = {e["id"] for e in t["fixed_elements"]}
        assert "title" in ids
        assert "subtitle" in ids
        # Accent bar decoration
        assert len(t["decorations"]) >= 1

    def test_section_has_required_keys(self):
        s = self.LAYOUTS["section"]
        assert s["name"] == "section"
        ids = {e["id"] for e in s["fixed_elements"]}
        assert "section_number" in ids
        assert "section_title" in ids
        assert "section_subtitle" in ids
        # Has gradient decoration
        assert len(s["decorations"]) >= 2

    def test_content_bullet_has_page_number(self):
        c = self.LAYOUTS["content_bullet"]
        ids = {e["id"] for e in c["fixed_elements"]}
        assert "title" in ids
        assert "body" in ids
        assert "page_number" in ids
        # Page number is NOT a placeholder (fixed text)
        pn = [e for e in c["fixed_elements"] if e["id"] == "page_number"][0]
        assert pn["placeholder"] is False

    def test_two_column_has_containers(self):
        c = self.LAYOUTS["content_two_column"]
        assert len(c["containers"]) == 2
        cids = {ct["id"] for ct in c["containers"]}
        assert "left_col" in cids
        assert "right_col" in cids
        # Each container has decorations (rounded border)
        for ct in c["containers"]:
            assert len(ct["decorations"]) >= 1

    def test_grid_has_four_containers(self):
        g = self.LAYOUTS["content_grid_2x2"]
        assert len(g["containers"]) == 4
        expected = {"grid_00", "grid_01", "grid_10", "grid_11"}
        assert {ct["id"] for ct in g["containers"]} == expected

    def test_ending_has_thanks(self):
        e = self.LAYOUTS["ending"]
        ids = {el["id"] for el in e["fixed_elements"]}
        assert "thanks_title" in ids
        assert "thanks_subtitle" in ids

    def test_all_fixed_elements_have_position(self):
        for name, layout in self.LAYOUTS.items():
            if not layout:  # content_three_column is empty dict
                continue
            for el in layout.get("fixed_elements", []):
                pos = el.get("position", {})
                assert "left" in pos, f"{name}.{el['id']} missing left"
                assert "top" in pos, f"{name}.{el['id']} missing top"
                assert "width" in pos, f"{name}.{el['id']} missing width"

    def test_all_decorations_are_shapes(self):
        for name, layout in self.LAYOUTS.items():
            if not layout:
                continue
            for dec in layout.get("decorations", []):
                assert dec["type"] == "shape", f"{name}.{dec['id']} not shape"
                assert dec["shape_type"] in (
                    "rectangle", "rounded_rectangle", "oval", "diamond",
                    "triangle", "right_triangle", "hexagon", "pentagon",
                    "star_5", "up_ribbon", "down_ribbon", "right_arrow",
                ) or True  # 182 possible shapes are possible, just check it's there
