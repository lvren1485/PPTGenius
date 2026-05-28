"""Tests for PPT agent common module — layout resolver, instruction loader, tools.

All tests are API-call-free (no LLM required).
"""

from __future__ import annotations

import json

import pytest

from pptgenius.agent.ppt.common.layout_resolver import (
    CONTAINER_BOUNDS,
    FORMAT_LAYOUT_MAP,
    LAYOUT_MAP,
    format_container_prompt,
    get_container_bounds,
    interpolate_layout,
    select_layout,
)
from pptgenius.agent.ppt.common.instruction_loader import (
    get_instruction,
    get_shared_instructions,
    list_chart_instructions,
)
from pptgenius.agent.ppt.layout.definitions import (
    CONTENT_BULLET,
    CONTENT_TWO_COLUMN,
    BUILTIN_LAYOUTS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Layout Resolver
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelectLayout:
    def test_title_maps_to_title_slide(self):
        assert select_layout({"layout_type": "title"}) == "title_slide"

    def test_section_maps_to_section(self):
        assert select_layout({"layout_type": "section"}) == "section"

    def test_summary_maps_to_content_bullet(self):
        assert select_layout({"layout_type": "summary"}) == "content_bullet"

    def test_thanks_maps_to_ending(self):
        assert select_layout({"layout_type": "thanks"}) == "ending"

    def test_content_defaults_to_content_bullet(self):
        assert (
            select_layout({
                "layout_type": "content",
                "content_json": {},
            })
            == "content_bullet"
        )

    def test_two_column_format_overrides_to_two_column(self):
        assert (
            select_layout({
                "layout_type": "content",
                "content_json": {"recommended_ppt_format": "two_column"},
            })
            == "content_two_column"
        )

    def test_comparison_format_overrides_to_two_column(self):
        assert (
            select_layout({
                "layout_type": "content",
                "content_json": {"recommended_ppt_format": "comparison"},
            })
            == "content_two_column"
        )

    def test_three_column_format_overrides(self):
        assert (
            select_layout({
                "layout_type": "content",
                "content_json": {"recommended_ppt_format": "three_column"},
            })
            == "content_three_column"
        )

    def test_four_grid_format_overrides(self):
        assert (
            select_layout({
                "layout_type": "content",
                "content_json": {"recommended_ppt_format": "four_grid"},
            })
            == "content_grid_2x2"
        )

    def test_unknown_format_keeps_content_bullet(self):
        assert (
            select_layout({
                "layout_type": "content",
                "content_json": {"recommended_ppt_format": "unknown_format"},
            })
            == "content_bullet"
        )

    def test_content_json_string_handled_gracefully(self):
        """If content_json is a JSON string, it's not a dict — fallback."""
        assert (
            select_layout({
                "layout_type": "content",
                "content_json": '{"recommended_ppt_format": "two_column"}',
            })
            == "content_bullet"
        )


class TestContainerBounds:
    def test_slide_bounds_exist(self):
        assert "slide" in CONTAINER_BOUNDS
        s = CONTAINER_BOUNDS["slide"]
        assert s["left"] == 0
        assert s["top"] == 0
        assert s["width"] == 13.333
        assert s["height"] == 7.5

    def test_all_grid_containers_exist(self):
        for cid in ("grid_00", "grid_01", "grid_10", "grid_11"):
            assert cid in CONTAINER_BOUNDS, f"Missing {cid}"

    def test_all_three_col_exist(self):
        for cid in ("col_0", "col_1", "col_2"):
            assert cid in CONTAINER_BOUNDS, f"Missing {cid}"

    def test_left_right_col_exist(self):
        assert "left_col" in CONTAINER_BOUNDS
        assert "right_col" in CONTAINER_BOUNDS

    def test_non_overlapping_two_column(self):
        left = CONTAINER_BOUNDS["left_col"]
        right = CONTAINER_BOUNDS["right_col"]
        assert left["left"] + left["width"] <= right["left"], "columns overlap"

    def test_non_overlapping_three_column(self):
        c0 = CONTAINER_BOUNDS["col_0"]
        c1 = CONTAINER_BOUNDS["col_1"]
        c2 = CONTAINER_BOUNDS["col_2"]
        assert c0["left"] + c0["width"] <= c1["left"]
        assert c1["left"] + c1["width"] <= c2["left"]

    def test_non_overlapping_grid(self):
        g00 = CONTAINER_BOUNDS["grid_00"]
        g01 = CONTAINER_BOUNDS["grid_01"]
        g10 = CONTAINER_BOUNDS["grid_10"]
        g11 = CONTAINER_BOUNDS["grid_11"]
        # Horizontal: g00 → g01
        assert g00["left"] + g00["width"] <= g01["left"]
        assert g10["left"] + g10["width"] <= g11["left"]
        # Vertical: g00 → g10
        assert g00["top"] + g00["height"] <= g10["top"]
        assert g01["top"] + g01["height"] <= g11["top"]

    def test_all_bounds_within_slide(self):
        sw, sh = 13.333, 7.5
        for cid, b in CONTAINER_BOUNDS.items():
            if cid == "slide":
                continue
            assert b["left"] >= 0, f"{cid}: left < 0"
            assert b["top"] >= 0, f"{cid}: top < 0"
            assert b["left"] + b["width"] <= sw + 0.01, (
                f"{cid}: right edge {b['left'] + b['width']} > {sw}"
            )
            assert b["top"] + b["height"] <= sh + 0.01, (
                f"{cid}: bottom edge {b['top'] + b['height']} > {sh}"
            )


class TestGetContainerBounds:
    def test_returns_slide_always(self):
        bounds = get_container_bounds({"containers": []})
        assert "slide" in bounds

    def test_extracts_layout_containers(self):
        bounds = get_container_bounds(CONTENT_TWO_COLUMN)
        assert "left_col" in bounds
        assert "right_col" in bounds

    def test_grid_extracts_four_containers(self):
        from pptgenius.agent.ppt.layout.definitions import CONTENT_GRID_2X2
        bounds = get_container_bounds(CONTENT_GRID_2X2)
        for cid in ("grid_00", "grid_01", "grid_10", "grid_11"):
            assert cid in bounds


class TestFormatContainerPrompt:
    def test_slide_container_uses_absolute(self):
        prompt = format_container_prompt(CONTAINER_BOUNDS, "slide")
        assert "绝对坐标" in prompt

    def test_other_parent_includes_bounds(self):
        prompt = format_container_prompt(CONTAINER_BOUNDS, "left_col")
        assert "parent='left_col'" in prompt
        assert "相对坐标" in prompt


class TestInterpolateLayout:
    def test_replaces_primary_color(self):
        cs = {"colors": {"primary": "ff0000", "bg": "ffffff", "border": "cccccc"}}
        layout = {
            "decorations": [
                {"fill": {"type": "solid", "color": "{{primary}}"}}
            ]
        }
        result = interpolate_layout(layout, cs)
        assert result["decorations"][0]["fill"]["color"] == "ff0000"

    def test_replaces_multiple_colors(self):
        cs = {"colors": {"primary": "ff0000", "accent": "00ff00", "bg": "ffffff", "border": "cccccc"}}
        layout = {
            "background": {"type": "solid", "color": "{{bg}}"},
            "decorations": [
                {"fill": {"type": "solid", "color": "{{primary}}"}},
                {"fill": {"type": "solid", "color": "{{accent}}"}},
            ]
        }
        result = interpolate_layout(layout, cs)
        assert result["background"]["color"] == "ffffff"
        assert result["decorations"][0]["fill"]["color"] == "ff0000"
        assert result["decorations"][1]["fill"]["color"] == "00ff00"

    def test_unchanged_for_no_variables(self):
        cs = {"colors": {"primary": "ff0000"}}
        layout = {"name": "test", "fixed_elements": [{"text": "Hello"}]}
        result = interpolate_layout(layout, cs)
        assert result["fixed_elements"][0]["text"] == "Hello"

    def test_does_not_mutate_original(self):
        cs = {"colors": {"primary": "ff0000"}}
        layout = {
            "decorations": [
                {"fill": {"type": "solid", "color": "{{primary}}"}}
            ]
        }
        original_color = layout["decorations"][0]["fill"]["color"]
        interpolate_layout(layout, cs)
        assert layout["decorations"][0]["fill"]["color"] == original_color

    def test_nested_containers_interpolated(self):
        cs = {"colors": {"primary": "111111", "bg": "ffffff", "border": "eeeeee"}}
        result = interpolate_layout(CONTENT_TWO_COLUMN, cs)
        # Title bar decoration
        title_bar = [d for d in result["decorations"] if d["id"] == "title_bar"][0]
        assert title_bar["fill"]["color"] == "111111"
        # Bottom line
        bottom_line = [d for d in result["decorations"] if d["id"] == "bottom_line"][0]
        assert bottom_line["fill"]["color"] == "eeeeee"
        # Container border
        left_col = [c for c in result["containers"] if c["id"] == "left_col"][0]
        border = left_col["decorations"][0]
        assert border["line"]["color"] == "eeeeee"

    def test_gradient_stops_interpolated(self):
        cs = {"colors": {"primary": "aa0000", "accent": "0000aa"}}
        layout = {
            "decorations": [{
                "fill": {
                    "type": "gradient",
                    "gradient_stops": [
                        {"position": 0.0, "color": "{{primary}}"},
                        {"position": 1.0, "color": "{{accent}}"},
                    ]
                }
            }]
        }
        result = interpolate_layout(layout, cs)
        stops = result["decorations"][0]["fill"]["gradient_stops"]
        assert stops[0]["color"] == "aa0000"
        assert stops[1]["color"] == "0000aa"


# ═══════════════════════════════════════════════════════════════════════════════
# Instruction Loader
# ═══════════════════════════════════════════════════════════════════════════════


class TestInstructionLoader:
    def test_get_textbox_instruction(self):
        data = get_instruction("textbox.json")
        assert data["type"] == "textbox"
        assert "fields" in data

    def test_get_table_instruction(self):
        data = get_instruction("table.json")
        assert data["type"] == "table"

    def test_get_shape_instruction(self):
        data = get_instruction("shape.json")
        assert data["type"] == "shape"

    def test_get_shape_catalog(self):
        data = get_instruction("shape_catalog.json")
        assert "groups" in data
        assert len(data["groups"]) >= 5

    def test_get_background_instruction(self):
        data = get_instruction("background.json")
        assert data["type"] == "background"

    def test_get_chart_instruction(self):
        data = get_instruction("chart/column.json")
        assert data["type"] == "chart"
        assert "chart_type" in data

    def test_get_picture_instruction(self):
        data = get_instruction("picture.json")
        assert data["type"] == "picture"

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            get_instruction("nonexistent.json")

    def test_cache_returns_same_object(self):
        a = get_instruction("textbox.json")
        b = get_instruction("textbox.json")
        assert a is b  # cached


class TestSharedInstructions:
    def test_loads_position(self):
        text = get_shared_instructions("position")
        assert "13.333" in text or "英寸" in text

    def test_loads_font(self):
        text = get_shared_instructions("font")
        assert "FontSpec" in text or "字体" in text or "font" in text.lower()

    def test_loads_fill(self):
        text = get_shared_instructions("fill")
        assert "gradient" in text or "solid" in text or "填充" in text

    def test_loads_line(self):
        text = get_shared_instructions("line")
        assert "dash" in text or "线条" in text or "line" in text.lower()

    def test_loads_multiple(self):
        text = get_shared_instructions("position", "font")
        assert len(text) > 0
        # Both should be present
        assert "position" in text.lower() or "位置" in text


class TestListChartInstructions:
    def test_returns_all_eight_chart_types(self):
        charts = list_chart_instructions()
        assert len(charts) == 8
        files = {c["file"] for c in charts}
        assert "chart/column.json" in files
        assert "chart/bar.json" in files
        assert "chart/line.json" in files
        assert "chart/pie.json" in files
        assert "chart/area.json" in files
        assert "chart/scatter.json" in files
        assert "chart/radar.json" in files
        assert "chart/bubble.json" in files

    def test_each_has_required_keys(self):
        for c in list_chart_instructions():
            assert "file" in c
            assert "chart_type" in c
            assert "description" in c


# ═══════════════════════════════════════════════════════════════════════════════
# Resource file validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestLayoutJsonFiles:
    """Validate all 7 layout JSON resource files."""

    LAYOUT_DIR = None
    REQUIRED_KEYS = {"name", "label", "background", "fixed_elements", "decorations", "containers"}

    @pytest.fixture(autouse=True)
    def _setup(self):
        from pathlib import Path
        from pptgenius.infrastructure.config import RESOURCES_DIR
        self.LAYOUT_DIR = RESOURCES_DIR / "layouts"

    def _load(self, name):
        return json.loads((self.LAYOUT_DIR / f"{name}.json").read_text(encoding="utf-8"))

    def test_all_seven_files_exist(self):
        for name in LAYOUT_MAP.values():
            assert (self.LAYOUT_DIR / f"{name}.json").exists(), f"Missing {name}.json"

    def test_all_have_required_keys(self):
        for name in LAYOUT_MAP.values():
            data = self._load(name)
            missing = self.REQUIRED_KEYS - set(data)
            assert not missing, f"{name} missing keys: {missing}"

    def test_fixed_elements_have_type_and_position(self):
        for name in LAYOUT_MAP.values():
            data = self._load(name)
            for el in data.get("fixed_elements", []):
                assert "type" in el, f"{name}.{el.get('id', '?')} missing type"
                assert "position" in el, f"{name}.{el.get('id', '?')} missing position"

    def test_decorations_are_shapes(self):
        for name in LAYOUT_MAP.values():
            data = self._load(name)
            for d in data.get("decorations", []):
                assert d["type"] == "shape", f"{name}.{d['id']} not shape"

    def test_container_ids_are_unique(self):
        for name in LAYOUT_MAP.values():
            data = self._load(name)
            cids = [c["id"] for c in data.get("containers", [])]
            assert len(cids) == len(set(cids)), f"{name} duplicate container ids"


class TestColorSchemeJsonFiles:
    """Validate all 4 color scheme JSON resource files."""

    CS_DIR = None

    @pytest.fixture(autouse=True)
    def _setup(self):
        from pathlib import Path
        from pptgenius.infrastructure.config import RESOURCES_DIR
        self.CS_DIR = RESOURCES_DIR / "color_schemes"

    def _load(self, name):
        return json.loads((self.CS_DIR / f"{name}.json").read_text(encoding="utf-8"))

    def test_all_four_exist(self):
        for name in ("business_blue", "academic_warm", "minimal_dark", "creative_vivid"):
            assert (self.CS_DIR / f"{name}.json").exists(), f"Missing {name}.json"

    def test_all_have_required_keys(self):
        required = {"name", "label", "style_density", "colors", "chart_colors", "fonts", "decoration"}
        for f in self.CS_DIR.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            missing = required - set(data)
            assert not missing, f"{f.name} missing: {missing}"

    def test_all_have_minimal_color_keys(self):
        color_keys = {"primary", "accent", "text", "text_secondary", "bg", "border"}
        for f in self.CS_DIR.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            missing = color_keys - set(data["colors"])
            assert not missing, f"{f.name} colors missing: {missing}"

    def test_all_have_four_font_styles(self):
        font_keys = {"title", "subtitle", "body", "caption"}
        for f in self.CS_DIR.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            missing = font_keys - set(data["fonts"])
            assert not missing, f"{f.name} fonts missing: {missing}"

    def test_chart_colors_are_list_of_six(self):
        for f in self.CS_DIR.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            cc = data["chart_colors"]
            assert isinstance(cc, list), f"{f.name}: chart_colors not list"
            assert len(cc) >= 4, f"{f.name}: need >=4 chart colors, got {len(cc)}"
            for c in cc:
                assert len(c) == 6, f"{f.name}: '{c}' not 6-char hex"

    def test_colors_are_valid_hex(self):
        import re
        hex_re = re.compile(r"^[0-9a-fA-F]{6}$")
        for f in self.CS_DIR.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            for key, val in data["colors"].items():
                assert hex_re.match(val), f"{f.name}.colors.{key}='{val}' not valid hex"

    def test_style_density_is_valid(self):
        valid = {"minimal", "moderate", "elaborate"}
        for f in self.CS_DIR.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            assert data["style_density"] in valid, (
                f"{f.name}: style_density='{data['style_density']}' not in {valid}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Outline prompt layout mapping consistency
# ═══════════════════════════════════════════════════════════════════════════════


class TestOutlinePromptConsistency:
    """Verify the outline prompt's layout_type mapping matches the code."""

    def test_layout_map_covers_outline_types(self):
        """Generator prompt mentions: title, section, content, summary, thanks."""
        outline_types = {"title", "section", "content", "summary", "thanks"}
        covered = set(LAYOUT_MAP)
        missing = outline_types - covered
        assert not missing, f"LAYOUT_MAP missing: {missing}"

    def test_format_map_has_all_relevant_formats(self):
        """Content overrides via recommended_ppt_format."""
        assert "two_column" in FORMAT_LAYOUT_MAP
        assert "comparison" in FORMAT_LAYOUT_MAP
        assert "three_column" in FORMAT_LAYOUT_MAP
        assert "four_grid" in FORMAT_LAYOUT_MAP
