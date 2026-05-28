"""Layout definitions — Python fallback constants for the 7 built-in layouts.

These are used when the DB doesn't have templates (before seed runs).
Primary source of truth: resources/layouts/*.json
"""

from __future__ import annotations

TITLE_SLIDE: dict = {
    "name": "title_slide",
    "label": "封面",
    "fixed_elements": [
        {"id": "title", "type": "textbox",
         "position": {"left": 1.0, "top": 2.2, "width": 11.3, "height": 1.5},
         "style_ref": "title", "placeholder": True},
        {"id": "subtitle", "type": "textbox",
         "position": {"left": 1.0, "top": 3.9, "width": 11.3, "height": 0.8},
         "style_ref": "subtitle", "placeholder": True},
    ],
    "decorations": [
        {"id": "title_accent_bar", "type": "shape", "shape_type": "rectangle",
         "position": {"left": 1.0, "top": 2.15, "width": 0.08, "height": 1.5},
         "fill": {"type": "solid", "color": "{{primary}}"}, "line": None},
    ],
    "containers": [],
}

SECTION: dict = {
    "name": "section",
    "label": "章节分隔页",
    "fixed_elements": [
        {"id": "section_number", "type": "textbox",
         "position": {"left": 0.8, "top": 2.0, "width": 2.0, "height": 1.2},
         "style_ref": "title", "placeholder": True},
        {"id": "section_title", "type": "textbox",
         "position": {"left": 0.8, "top": 3.3, "width": 11.7, "height": 1.0},
         "style_ref": "title", "placeholder": True},
        {"id": "section_subtitle", "type": "textbox",
         "position": {"left": 0.8, "top": 4.5, "width": 11.7, "height": 0.6},
         "style_ref": "subtitle", "placeholder": True},
    ],
    "decorations": [
        {"id": "section_number_bg", "type": "shape", "shape_type": "rounded_rectangle",
         "position": {"left": 0.8, "top": 1.8, "width": 2.5, "height": 3.2},
         "fill": {"type": "gradient", "gradient_angle": 135,
                  "gradient_stops": [{"position": 0.0, "color": "{{primary}}"},
                                    {"position": 1.0, "color": "{{accent}}"}]},
         "line": None},
        {"id": "divider_line", "type": "shape", "shape_type": "rectangle",
         "position": {"left": 0.8, "top": 5.8, "width": 11.7, "height": 0.015},
         "fill": {"type": "solid", "color": "{{border}}"}, "line": None},
    ],
    "containers": [],
}

CONTENT_BULLET: dict = {
    "name": "content_bullet",
    "label": "标题 + 正文",
    "fixed_elements": [
        {"id": "title", "type": "textbox",
         "position": {"left": 0.8, "top": 0.4, "width": 11.7, "height": 0.9},
         "style_ref": "title", "placeholder": True},
        {"id": "body", "type": "textbox",
         "position": {"left": 1.2, "top": 1.6, "width": 10.9, "height": 5.1},
         "style_ref": "body", "placeholder": True},
        {"id": "page_number", "type": "textbox",
         "position": {"left": 11.8, "top": 6.9, "width": 1.0, "height": 0.4},
         "style_ref": "caption", "text": "{page_num} / {total_pages}", "placeholder": False},
    ],
    "decorations": [
        {"id": "title_bar", "type": "shape", "shape_type": "rectangle",
         "position": {"left": 0.8, "top": 0.35, "width": 0.08, "height": 0.55},
         "fill": {"type": "solid", "color": "{{primary}}"}, "line": None},
        {"id": "bottom_line", "type": "shape", "shape_type": "rectangle",
         "position": {"left": 0.8, "top": 6.95, "width": 11.7, "height": 0.01},
         "fill": {"type": "solid", "color": "{{border}}"}, "line": None},
    ],
    "containers": [],
}

_MAKE_COL_BG = lambda cid: {
    "id": f"{cid}_bg", "type": "shape", "shape_type": "rounded_rectangle",
    "position": {"left": 0, "top": 0, "width": 5.8, "height": 5.1},
    "fill": {"type": "no_fill"}, "line": {"color": "{{border}}", "width_pt": 0.5},
}

CONTENT_TWO_COLUMN: dict = {
    "name": "content_two_column",
    "label": "标题 + 两栏",
    "fixed_elements": [
        {"id": "title", "type": "textbox",
         "position": {"left": 0.8, "top": 0.4, "width": 11.7, "height": 0.9},
         "style_ref": "title", "placeholder": True},
        {"id": "page_number", "type": "textbox",
         "position": {"left": 11.8, "top": 6.9, "width": 1.0, "height": 0.4},
         "style_ref": "caption", "text": "{page_num} / {total_pages}", "placeholder": False},
    ],
    "decorations": [
        {"id": "title_bar", "type": "shape", "shape_type": "rectangle",
         "position": {"left": 0.8, "top": 0.35, "width": 0.08, "height": 0.55},
         "fill": {"type": "solid", "color": "{{primary}}"}, "line": None},
        {"id": "bottom_line", "type": "shape", "shape_type": "rectangle",
         "position": {"left": 0.8, "top": 6.95, "width": 11.7, "height": 0.01},
         "fill": {"type": "solid", "color": "{{border}}"}, "line": None},
    ],
    "containers": [
        {"id": "left_col", "label": "左栏",
         "position": {"left": 0.5, "top": 1.6, "width": 5.8, "height": 5.1},
         "decorations": [_MAKE_COL_BG("left_col")]},
        {"id": "right_col", "label": "右栏",
         "position": {"left": 6.8, "top": 1.6, "width": 5.8, "height": 5.1},
         "decorations": [_MAKE_COL_BG("right_col")]},
    ],
}

_GRID_DEC = lambda cid, w, h: {
    "id": f"{cid}_bg", "type": "shape", "shape_type": "rounded_rectangle",
    "position": {"left": 0, "top": 0, "width": w, "height": h},
    "fill": {"type": "no_fill"}, "line": {"color": "{{border}}", "width_pt": 0.5},
}

CONTENT_GRID_2X2: dict = {
    "name": "content_grid_2x2",
    "label": "标题 + 2×2 网格",
    "fixed_elements": [
        {"id": "title", "type": "textbox",
         "position": {"left": 0.8, "top": 0.4, "width": 11.7, "height": 0.9},
         "style_ref": "title", "placeholder": True},
        {"id": "page_number", "type": "textbox",
         "position": {"left": 11.8, "top": 6.9, "width": 1.0, "height": 0.4},
         "style_ref": "caption", "text": "{page_num} / {total_pages}", "placeholder": False},
    ],
    "decorations": [
        {"id": "title_bar", "type": "shape", "shape_type": "rectangle",
         "position": {"left": 0.8, "top": 0.35, "width": 0.08, "height": 0.55},
         "fill": {"type": "solid", "color": "{{primary}}"}, "line": None},
        {"id": "bottom_line", "type": "shape", "shape_type": "rectangle",
         "position": {"left": 0.8, "top": 6.95, "width": 11.7, "height": 0.01},
         "fill": {"type": "solid", "color": "{{border}}"}, "line": None},
    ],
    "containers": [
        {"id": "grid_00", "label": "左上", "position": {"left": 0.5, "top": 1.6, "width": 5.8, "height": 2.5},
         "decorations": [_GRID_DEC("grid_00", 5.8, 2.5)]},
        {"id": "grid_01", "label": "右上", "position": {"left": 6.8, "top": 1.6, "width": 5.8, "height": 2.5},
         "decorations": [_GRID_DEC("grid_01", 5.8, 2.5)]},
        {"id": "grid_10", "label": "左下", "position": {"left": 0.5, "top": 4.3, "width": 5.8, "height": 2.5},
         "decorations": [_GRID_DEC("grid_10", 5.8, 2.5)]},
        {"id": "grid_11", "label": "右下", "position": {"left": 6.8, "top": 4.3, "width": 5.8, "height": 2.5},
         "decorations": [_GRID_DEC("grid_11", 5.8, 2.5)]},
    ],
}

ENDING: dict = {
    "name": "ending",
    "label": "结尾/致谢",
    "fixed_elements": [
        {"id": "thanks_title", "type": "textbox",
         "position": {"left": 1.0, "top": 2.5, "width": 11.3, "height": 1.5},
         "style_ref": "title", "placeholder": True},
        {"id": "thanks_subtitle", "type": "textbox",
         "position": {"left": 1.0, "top": 4.2, "width": 11.3, "height": 0.8},
         "style_ref": "subtitle", "placeholder": True},
    ],
    "decorations": [
        {"id": "ending_accent", "type": "shape", "shape_type": "rounded_rectangle",
         "position": {"left": 4.0, "top": 1.8, "width": 5.3, "height": 3.8},
         "fill": {"type": "no_fill"}, "line": {"color": "{{primary}}", "width_pt": 2.0}},
    ],
    "containers": [],
}

BUILTIN_LAYOUTS: dict[str, dict] = {
    "title_slide": TITLE_SLIDE,
    "section": SECTION,
    "content_bullet": CONTENT_BULLET,
    "content_two_column": CONTENT_TWO_COLUMN,
    "content_three_column": {},  # loaded from resources
    "content_grid_2x2": CONTENT_GRID_2X2,
    "ending": ENDING,
}
