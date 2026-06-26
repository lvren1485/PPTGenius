"""Static tests for spatial_check — coverage of check_element and check_plan_bounds."""

import pytest

from pptgenius.agent.ppt.spatial_check import check_element, check_plan_bounds


# ── geometry helpers (private, tested via public API) ─────────────────

def _make_pos(left=0, top=0, width=1.0, height=1.0, z_order=70):
    return {"left": left, "top": top, "width": width, "height": height, "z_order": z_order}


def _make_el(el_type="textbox", pos=None, **extra):
    return {"type": el_type, "position": pos or _make_pos(), **extra}


def _make_buffer(*elements):
    buf = {"elements": {}}
    for i, el in enumerate(elements):
        buf["elements"][f"el_{i}"] = el
    return buf


# ═══════════════════════════════════════════════════════════════════════
# check_element
# ═══════════════════════════════════════════════════════════════════════

class TestCheckElementEmpty:
    """No-warning cases — should return empty string."""

    def test_no_position(self):
        el = {"type": "textbox"}
        assert check_element(el, _make_buffer()) == ""

    def test_empty_buffer_normal_element(self):
        el = _make_el("textbox", _make_pos(1, 1, 4, 3))
        assert check_element(el, _make_buffer()) == ""

    def test_different_z_order_no_overlap_warning(self):
        """Overlap is only flagged for same-layer (±10 z)."""
        existing = _make_el("shape", _make_pos(0, 0, 3, 3, z_order=20))
        new_el = _make_el("textbox", _make_pos(0, 0, 3, 3, z_order=80))
        result = check_element(new_el, _make_buffer(existing))
        # z diff > 10 → no overlap warning
        assert "重叠" not in result


class TestCheckElementOverlap:
    def test_full_overlap_same_layer(self):
        existing = _make_el("textbox", _make_pos(1, 1, 2, 2, z_order=70))
        new_el = _make_el("textbox", _make_pos(1, 1, 2, 2, z_order=70))
        result = check_element(new_el, _make_buffer(existing))
        assert "重叠" in result
        assert "100%" in result

    def test_partial_overlap_same_layer(self):
        existing = _make_el("textbox", _make_pos(0, 0, 2, 2, z_order=70))
        new_el = _make_el("textbox", _make_pos(1, 1, 2, 2, z_order=70))
        result = check_element(new_el, _make_buffer(existing))
        assert "重叠" in result
        assert "25%" in result or "重叠" in result  # ~25% of 2x2

    def test_adjacent_no_overlap(self):
        existing = _make_el("textbox", _make_pos(0, 0, 2, 2, z_order=70))
        new_el = _make_el("textbox", _make_pos(2, 0, 2, 2, z_order=70))
        result = check_element(new_el, _make_buffer(existing))
        assert "重叠" not in result

    def test_overlap_nearby_z_order(self):
        """z diff ≤ 10 should still flag overlap."""
        existing = _make_el("textbox", _make_pos(1, 1, 2, 2, z_order=65))
        new_el = _make_el("textbox", _make_pos(1, 1, 2, 2, z_order=70))
        result = check_element(new_el, _make_buffer(existing))
        assert "重叠" in result


# ═══════════════════════════════════════════════════════════════════════
# B3: minimum size
# ═══════════════════════════════════════════════════════════════════════

class TestCheckElementMinSize:
    def test_table_too_short(self):
        el = _make_el("table", _make_pos(0, 0, 5, 0.3), rows=5)
        result = check_element(el, _make_buffer())
        assert "表格每行" in result

    def test_table_ok(self):
        el = _make_el("table", _make_pos(0, 0, 5, 3.0), rows=5)
        result = check_element(el, _make_buffer())
        assert "表格每行" not in result

    def test_chart_too_small(self):
        el = _make_el("chart", _make_pos(0, 0, 1.0, 1.0))
        result = check_element(el, _make_buffer())
        assert "图表尺寸过小" in result

    def test_chart_ok(self):
        el = _make_el("chart", _make_pos(0, 0, 3.0, 2.5))
        result = check_element(el, _make_buffer())
        assert "图表" not in result

    def test_chart_too_flat(self):
        el = _make_el("chart", _make_pos(0, 0, 8.0, 1.0))
        result = check_element(el, _make_buffer())
        assert "扁平" in result

    def test_chart_too_tall(self):
        el = _make_el("chart", _make_pos(0, 0, 1.0, 5.0))
        result = check_element(el, _make_buffer())
        assert "细长" in result

    def test_table_too_flat(self):
        el = _make_el("table", _make_pos(0, 0, 10.0, 0.5), rows=3)
        result = check_element(el, _make_buffer())
        assert "扁平" in result

    def test_table_narrow_columns(self):
        el = _make_el("table", _make_pos(0, 0, 2.0, 3.0), rows=3, cols=6)
        result = check_element(el, _make_buffer())
        assert "过窄" in result

    def test_picture_too_flat(self):
        el = _make_el("picture", _make_pos(0, 0, 10.0, 1.0))
        result = check_element(el, _make_buffer())
        assert "扁平" in result

    def test_picture_too_small(self):
        el = _make_el("picture", _make_pos(0, 0, 0.2, 0.2))
        result = check_element(el, _make_buffer())
        assert "图片尺寸过小" in result

    def test_generic_too_narrow(self):
        el = _make_el("shape", _make_pos(0, 0, 0.3, 1.0))
        result = check_element(el, _make_buffer())
        assert "宽度" in result and "过小" in result

    def test_generic_too_short(self):
        el = _make_el("shape", _make_pos(0, 0, 2.0, 0.1))
        result = check_element(el, _make_buffer())
        assert "高度" in result and "过小" in result


# ═══════════════════════════════════════════════════════════════════════
# B2: text overflow
# ═══════════════════════════════════════════════════════════════════════

class TestCheckElementTextOverflow:
    def test_text_fits(self):
        el = _make_el("textbox", _make_pos(0, 0, 6, 3), content=[
            {"paragraph": {"runs": [{"text": "短文本", "font": {"size": 16}}]}}
        ])
        result = check_element(el, _make_buffer())
        assert "文字可能溢出" not in result

    def test_text_overflow(self):
        """Cram 2000 chars into a tiny box — should warn."""
        el = _make_el("textbox", _make_pos(0, 0, 1, 0.3), content=[
            {"paragraph": {"runs": [{"text": "X" * 2000, "font": {"size": 16}}]}}
        ])
        result = check_element(el, _make_buffer())
        assert "文字可能溢出" in result

    def test_no_font_size_no_warning(self):
        """If font size is not specified, skip overflow check."""
        el = _make_el("textbox", _make_pos(0, 0, 1, 0.3), content=[
            {"paragraph": {"runs": [{"text": "X" * 2000}]}}
        ])
        result = check_element(el, _make_buffer())
        assert "文字可能溢出" not in result


# ═══════════════════════════════════════════════════════════════════════
# B4: layer area
# ═══════════════════════════════════════════════════════════════════════

class TestCheckElementLayerArea:
    def test_layer_area_warning_high(self):
        """Fill most of the slide in one layer → should warn."""
        existing = _make_el("textbox", _make_pos(0, 0, 11, 7, z_order=70))
        new_el = _make_el("textbox", _make_pos(2, 1, 3, 2, z_order=70))
        result = check_element(new_el, _make_buffer(existing))
        assert "当前层" in result

    def test_layer_area_low(self):
        new_el = _make_el("textbox", _make_pos(0, 0, 2, 1, z_order=70))
        result = check_element(new_el, _make_buffer())
        assert "当前层" not in result

    def test_different_layer_not_counted(self):
        """Elements at z=20 should not count toward z=70 layer."""
        existing = _make_el("shape", _make_pos(0, 0, 10, 7, z_order=20))
        new_el = _make_el("textbox", _make_pos(0, 0, 2, 1, z_order=70))
        result = check_element(new_el, _make_buffer(existing))
        assert "当前层" not in result


# ═══════════════════════════════════════════════════════════════════════
# check_plan_bounds
# ═══════════════════════════════════════════════════════════════════════

class TestCheckPlanBounds:
    def test_empty_parts(self):
        assert check_plan_bounds({}) == []

    def test_no_bounds_in_parts(self):
        parts = {"标题区": {"description": "标题", "status": "pending"}}
        assert check_plan_bounds(parts) == []

    def test_part_overlap(self):
        parts = {
            "A": {"bounds": {"left": 0, "top": 0, "width": 5, "height": 4}, "status": "pending"},
            "B": {"bounds": {"left": 3, "top": 2, "width": 5, "height": 4}, "status": "pending"},
        }
        result = check_plan_bounds(parts)
        assert any("空间重叠" in w for w in result)

    def test_non_overlapping_parts_ok(self):
        parts = {
            "A": {"bounds": {"left": 0, "top": 0, "width": 6, "height": 3}, "status": "pending"},
            "B": {"bounds": {"left": 7, "top": 0, "width": 6, "height": 3}, "status": "pending"},
        }
        result = check_plan_bounds(parts)
        assert all("空间重叠" not in w for w in result)

    def test_canvas_overflow(self):
        parts = {
            "A": {"bounds": {"left": 10, "top": 0, "width": 5, "height": 3}, "status": "pending"},
        }
        result = check_plan_bounds(parts)
        assert any("超出画布" in w for w in result)

    def test_chart_too_small_for_part(self):
        parts = {
            "图表": {"bounds": {"left": 0, "top": 1, "width": 1, "height": 1}, "has_chart": True},
        }
        result = check_plan_bounds(parts)
        assert any("图表" in w for w in result)

    def test_table_too_small_for_part(self):
        parts = {
            "表格": {"bounds": {"left": 0, "top": 1, "width": 2, "height": 1}, "has_table": True},
        }
        result = check_plan_bounds(parts)
        assert any("表格" in w for w in result)

    def test_image_too_small_for_part(self):
        parts = {
            "图标": {"bounds": {"left": 0, "top": 0, "width": 0.3, "height": 0.3}, "has_image": True},
        }
        result = check_plan_bounds(parts)
        assert any("图片" in w for w in result)

    def test_total_area_warning(self):
        """Four large parts → exceeds 75% canvas."""
        parts = {}
        for i, name in enumerate(["A", "B", "C", "D"]):
            parts[name] = {"bounds": {"left": 0, "top": i * 2, "width": 12, "height": 2.0}}
        result = check_plan_bounds(parts)
        assert any("总面积" in w for w in result)

    def test_plan_chart_too_flat(self):
        parts = {
            "图表区": {"bounds": {"left": 1, "top": 2, "width": 8, "height": 1}, "has_chart": True},
        }
        result = check_plan_bounds(parts)
        assert any("扁平" in w for w in result)

    def test_mixed_with_and_without_bounds(self):
        """Parts without bounds should be ignored."""
        parts = {
            "A": {"bounds": {"left": 10, "top": 0, "width": 5, "height": 3}},
            "B": {"description": "no bounds here"},
        }
        result = check_plan_bounds(parts)
        assert any("超出画布" in w for w in result)
        assert len(result) == 1  # only the overflow for A, B ignored
