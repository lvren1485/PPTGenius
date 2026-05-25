"""Supported AutoShape catalog for JSON validation and LLM prompts.

182 MSO_SHAPE types organized into 9 semantic groups.
LLM selects shapes by ``shape_key``; the parser maps to ``MSO_SHAPE`` enum.
"""

from pptx.enum.shapes import MSO_SHAPE

# ── Semantic group → (shape_key, MSO_SHAPE) mapping ──
# shape_key is the LLM-facing identifier; MSO_SHAPE is the python-pptx enum.

SHAPE_GROUPS: dict[str, dict[str, MSO_SHAPE]] = {
    # ── 基础几何 Basic Geometric ──
    "basic_geometric": {
        "rectangle":               MSO_SHAPE.RECTANGLE,
        "rounded_rectangle":       MSO_SHAPE.ROUNDED_RECTANGLE,
        "round_1_rectangle":       MSO_SHAPE.ROUND_1_RECTANGLE,
        "round_2_same_rectangle":  MSO_SHAPE.ROUND_2_SAME_RECTANGLE,
        "round_2_diag_rectangle":  MSO_SHAPE.ROUND_2_DIAG_RECTANGLE,
        "snip_1_rectangle":        MSO_SHAPE.SNIP_1_RECTANGLE,
        "snip_2_same_rectangle":   MSO_SHAPE.SNIP_2_SAME_RECTANGLE,
        "snip_2_diag_rectangle":   MSO_SHAPE.SNIP_2_DIAG_RECTANGLE,
        "snip_round_rectangle":    MSO_SHAPE.SNIP_ROUND_RECTANGLE,
        "folded_corner":           MSO_SHAPE.FOLDED_CORNER,
        "oval":                    MSO_SHAPE.OVAL,
        "diamond":                 MSO_SHAPE.DIAMOND,
        "triangle":                MSO_SHAPE.ISOSCELES_TRIANGLE,
        "right_triangle":          MSO_SHAPE.RIGHT_TRIANGLE,
        "parallelogram":           MSO_SHAPE.PARALLELOGRAM,
        "trapezoid":               MSO_SHAPE.TRAPEZOID,
        "pentagon":                MSO_SHAPE.PENTAGON,
        "hexagon":                 MSO_SHAPE.HEXAGON,
        "heptagon":                MSO_SHAPE.HEPTAGON,
        "octagon":                 MSO_SHAPE.OCTAGON,
        "decagon":                 MSO_SHAPE.DECAGON,
        "dodecagon":               MSO_SHAPE.DODECAGON,
        "cross":                   MSO_SHAPE.CROSS,
        "cube":                    MSO_SHAPE.CUBE,
        "bevel":                   MSO_SHAPE.BEVEL,
        "can":                     MSO_SHAPE.CAN,
        "donut":                   MSO_SHAPE.DONUT,
        "frame":                   MSO_SHAPE.FRAME,
        "half_frame":              MSO_SHAPE.HALF_FRAME,
        "plaque":                  MSO_SHAPE.PLAQUE,
        "plaque_tabs":             MSO_SHAPE.PLAQUE_TABS,
        "square_tabs":             MSO_SHAPE.SQUARE_TABS,
        "corner":                  MSO_SHAPE.CORNER,
        "corner_tabs":             MSO_SHAPE.CORNER_TABS,
        "heart":                   MSO_SHAPE.HEART,
        "moon":                    MSO_SHAPE.MOON,
        "sun":                     MSO_SHAPE.SUN,
        "tear":                    MSO_SHAPE.TEAR,
        "cloud":                   MSO_SHAPE.CLOUD,
        "lightning_bolt":          MSO_SHAPE.LIGHTNING_BOLT,
        "no_symbol":               MSO_SHAPE.NO_SYMBOL,
        "smiley_face":             MSO_SHAPE.SMILEY_FACE,
        "wave":                    MSO_SHAPE.WAVE,
        "double_wave":             MSO_SHAPE.DOUBLE_WAVE,
        "funnel":                  MSO_SHAPE.FUNNEL,
        "gear_6":                  MSO_SHAPE.GEAR_6,
        "gear_9":                  MSO_SHAPE.GEAR_9,
        "arc":                     MSO_SHAPE.ARC,
        "block_arc":               MSO_SHAPE.BLOCK_ARC,
        "chord":                   MSO_SHAPE.CHORD,
        "pie":                     MSO_SHAPE.PIE,
        "pie_wedge":               MSO_SHAPE.PIE_WEDGE,
    },

    # ── 星形 Stars ──
    "stars": {
        "star_4":     MSO_SHAPE.STAR_4_POINT,
        "star_5":     MSO_SHAPE.STAR_5_POINT,
        "star_6":     MSO_SHAPE.STAR_6_POINT,
        "star_7":     MSO_SHAPE.STAR_7_POINT,
        "star_8":     MSO_SHAPE.STAR_8_POINT,
        "star_10":    MSO_SHAPE.STAR_10_POINT,
        "star_12":    MSO_SHAPE.STAR_12_POINT,
        "star_16":    MSO_SHAPE.STAR_16_POINT,
        "star_24":    MSO_SHAPE.STAR_24_POINT,
        "star_32":    MSO_SHAPE.STAR_32_POINT,
        "explosion_1": MSO_SHAPE.EXPLOSION1,
        "explosion_2": MSO_SHAPE.EXPLOSION2,
    },

    # ── 块箭头 Block Arrows ──
    "arrows": {
        "right_arrow":             MSO_SHAPE.RIGHT_ARROW,
        "left_arrow":              MSO_SHAPE.LEFT_ARROW,
        "up_arrow":                MSO_SHAPE.UP_ARROW,
        "down_arrow":              MSO_SHAPE.DOWN_ARROW,
        "left_right_arrow":        MSO_SHAPE.LEFT_RIGHT_ARROW,
        "up_down_arrow":           MSO_SHAPE.UP_DOWN_ARROW,
        "quad_arrow":              MSO_SHAPE.QUAD_ARROW,
        "left_up_arrow":           MSO_SHAPE.LEFT_UP_ARROW,
        "bent_arrow":              MSO_SHAPE.BENT_ARROW,
        "bent_up_arrow":           MSO_SHAPE.BENT_UP_ARROW,
        "u_turn_arrow":            MSO_SHAPE.U_TURN_ARROW,
        "circular_arrow":          MSO_SHAPE.CIRCULAR_ARROW,
        "left_right_circular_arrow": MSO_SHAPE.LEFT_RIGHT_CIRCULAR_ARROW,
        "curved_right_arrow":      MSO_SHAPE.CURVED_RIGHT_ARROW,
        "curved_left_arrow":       MSO_SHAPE.CURVED_LEFT_ARROW,
        "curved_up_arrow":         MSO_SHAPE.CURVED_UP_ARROW,
        "curved_down_arrow":       MSO_SHAPE.CURVED_DOWN_ARROW,
        "striped_right_arrow":     MSO_SHAPE.STRIPED_RIGHT_ARROW,
        "notched_right_arrow":     MSO_SHAPE.NOTCHED_RIGHT_ARROW,
        "swoosh_arrow":            MSO_SHAPE.SWOOSH_ARROW,
        "left_right_up_arrow":     MSO_SHAPE.LEFT_RIGHT_UP_ARROW,
    },

    # ── 标注 Callouts ──
    "callouts": {
        "rectangular_callout":          MSO_SHAPE.RECTANGULAR_CALLOUT,
        "rounded_rectangular_callout":  MSO_SHAPE.ROUNDED_RECTANGULAR_CALLOUT,
        "oval_callout":                 MSO_SHAPE.OVAL_CALLOUT,
        "cloud_callout":                MSO_SHAPE.CLOUD_CALLOUT,
        "balloon":                      MSO_SHAPE.BALLOON,
        "line_callout_1":               MSO_SHAPE.LINE_CALLOUT_1,
        "line_callout_2":               MSO_SHAPE.LINE_CALLOUT_2,
        "line_callout_3":               MSO_SHAPE.LINE_CALLOUT_3,
        "line_callout_4":               MSO_SHAPE.LINE_CALLOUT_4,
        "line_callout_1_accent_bar":    MSO_SHAPE.LINE_CALLOUT_1_ACCENT_BAR,
        "line_callout_2_accent_bar":    MSO_SHAPE.LINE_CALLOUT_2_ACCENT_BAR,
        "line_callout_3_accent_bar":    MSO_SHAPE.LINE_CALLOUT_3_ACCENT_BAR,
        "line_callout_4_accent_bar":    MSO_SHAPE.LINE_CALLOUT_4_ACCENT_BAR,
        "line_callout_1_no_border":     MSO_SHAPE.LINE_CALLOUT_1_NO_BORDER,
        "line_callout_2_no_border":     MSO_SHAPE.LINE_CALLOUT_2_NO_BORDER,
        "line_callout_3_no_border":     MSO_SHAPE.LINE_CALLOUT_3_NO_BORDER,
        "line_callout_4_no_border":     MSO_SHAPE.LINE_CALLOUT_4_NO_BORDER,
        "line_callout_1_border_accent": MSO_SHAPE.LINE_CALLOUT_1_BORDER_AND_ACCENT_BAR,
        "line_callout_2_border_accent": MSO_SHAPE.LINE_CALLOUT_2_BORDER_AND_ACCENT_BAR,
        "line_callout_3_border_accent": MSO_SHAPE.LINE_CALLOUT_3_BORDER_AND_ACCENT_BAR,
        "line_callout_4_border_accent": MSO_SHAPE.LINE_CALLOUT_4_BORDER_AND_ACCENT_BAR,
        "down_arrow_callout":           MSO_SHAPE.DOWN_ARROW_CALLOUT,
        "up_arrow_callout":             MSO_SHAPE.UP_ARROW_CALLOUT,
        "left_arrow_callout":           MSO_SHAPE.LEFT_ARROW_CALLOUT,
        "right_arrow_callout":          MSO_SHAPE.RIGHT_ARROW_CALLOUT,
        "left_right_arrow_callout":     MSO_SHAPE.LEFT_RIGHT_ARROW_CALLOUT,
        "up_down_arrow_callout":        MSO_SHAPE.UP_DOWN_ARROW_CALLOUT,
        "quad_arrow_callout":           MSO_SHAPE.QUAD_ARROW_CALLOUT,
    },

    # ── 流程图 Flowchart ──
    "flowchart": {
        "flowchart_process":            MSO_SHAPE.FLOWCHART_PROCESS,
        "flowchart_decision":           MSO_SHAPE.FLOWCHART_DECISION,
        "flowchart_data":               MSO_SHAPE.FLOWCHART_DATA,
        "flowchart_document":           MSO_SHAPE.FLOWCHART_DOCUMENT,
        "flowchart_multidocument":      MSO_SHAPE.FLOWCHART_MULTIDOCUMENT,
        "flowchart_predefined_process": MSO_SHAPE.FLOWCHART_PREDEFINED_PROCESS,
        "flowchart_alternate_process":  MSO_SHAPE.FLOWCHART_ALTERNATE_PROCESS,
        "flowchart_terminator":         MSO_SHAPE.FLOWCHART_TERMINATOR,
        "flowchart_preparation":        MSO_SHAPE.FLOWCHART_PREPARATION,
        "flowchart_manual_input":       MSO_SHAPE.FLOWCHART_MANUAL_INPUT,
        "flowchart_manual_operation":   MSO_SHAPE.FLOWCHART_MANUAL_OPERATION,
        "flowchart_connector":          MSO_SHAPE.FLOWCHART_CONNECTOR,
        "flowchart_offpage_connector":  MSO_SHAPE.FLOWCHART_OFFPAGE_CONNECTOR,
        "flowchart_card":               MSO_SHAPE.FLOWCHART_CARD,
        "flowchart_punched_tape":       MSO_SHAPE.FLOWCHART_PUNCHED_TAPE,
        "flowchart_display":            MSO_SHAPE.FLOWCHART_DISPLAY,
        "flowchart_delay":              MSO_SHAPE.FLOWCHART_DELAY,
        "flowchart_extract":            MSO_SHAPE.FLOWCHART_EXTRACT,
        "flowchart_merge":              MSO_SHAPE.FLOWCHART_MERGE,
        "flowchart_or":                 MSO_SHAPE.FLOWCHART_OR,
        "flowchart_sort":               MSO_SHAPE.FLOWCHART_SORT,
        "flowchart_summing_junction":   MSO_SHAPE.FLOWCHART_SUMMING_JUNCTION,
        "flowchart_collate":            MSO_SHAPE.FLOWCHART_COLLATE,
        "flowchart_internal_storage":   MSO_SHAPE.FLOWCHART_INTERNAL_STORAGE,
        "flowchart_stored_data":        MSO_SHAPE.FLOWCHART_STORED_DATA,
        "flowchart_sequential_access":  MSO_SHAPE.FLOWCHART_SEQUENTIAL_ACCESS_STORAGE,
        "flowchart_magnetic_disk":      MSO_SHAPE.FLOWCHART_MAGNETIC_DISK,
        "flowchart_direct_access":      MSO_SHAPE.FLOWCHART_DIRECT_ACCESS_STORAGE,
    },

    # ── 带状横幅 Ribbons & Banners ──
    "ribbons": {
        "up_ribbon":              MSO_SHAPE.UP_RIBBON,
        "down_ribbon":            MSO_SHAPE.DOWN_RIBBON,
        "curved_up_ribbon":       MSO_SHAPE.CURVED_UP_RIBBON,
        "curved_down_ribbon":     MSO_SHAPE.CURVED_DOWN_RIBBON,
        "left_right_ribbon":      MSO_SHAPE.LEFT_RIGHT_RIBBON,
    },

    # ── 数学符号 Math ──
    "math": {
        "math_plus":      MSO_SHAPE.MATH_PLUS,
        "math_minus":     MSO_SHAPE.MATH_MINUS,
        "math_multiply":  MSO_SHAPE.MATH_MULTIPLY,
        "math_divide":    MSO_SHAPE.MATH_DIVIDE,
        "math_equal":     MSO_SHAPE.MATH_EQUAL,
        "math_not_equal": MSO_SHAPE.MATH_NOT_EQUAL,
    },

    # ── 动作按钮 Action Buttons ──
    "action_buttons": {
        "action_home":       MSO_SHAPE.ACTION_BUTTON_HOME,
        "action_help":       MSO_SHAPE.ACTION_BUTTON_HELP,
        "action_information": MSO_SHAPE.ACTION_BUTTON_INFORMATION,
        "action_back":       MSO_SHAPE.ACTION_BUTTON_BACK_OR_PREVIOUS,
        "action_next":       MSO_SHAPE.ACTION_BUTTON_FORWARD_OR_NEXT,
        "action_begin":      MSO_SHAPE.ACTION_BUTTON_BEGINNING,
        "action_end":        MSO_SHAPE.ACTION_BUTTON_END,
        "action_return":     MSO_SHAPE.ACTION_BUTTON_RETURN,
        "action_document":   MSO_SHAPE.ACTION_BUTTON_DOCUMENT,
        "action_sound":      MSO_SHAPE.ACTION_BUTTON_SOUND,
        "action_movie":      MSO_SHAPE.ACTION_BUTTON_MOVIE,
        "action_custom":     MSO_SHAPE.ACTION_BUTTON_CUSTOM,
    },

    # ── 其他 Miscellaneous ──
    "misc": {
        "chevron":              MSO_SHAPE.CHEVRON,
        "left_bracket":         MSO_SHAPE.LEFT_BRACKET,
        "right_bracket":        MSO_SHAPE.RIGHT_BRACKET,
        "left_brace":           MSO_SHAPE.LEFT_BRACE,
        "right_brace":          MSO_SHAPE.RIGHT_BRACE,
        "double_bracket":       MSO_SHAPE.DOUBLE_BRACKET,
        "double_brace":         MSO_SHAPE.DOUBLE_BRACE,
        "horizontal_scroll":    MSO_SHAPE.HORIZONTAL_SCROLL,
        "vertical_scroll":      MSO_SHAPE.VERTICAL_SCROLL,
        "chart_plus":           MSO_SHAPE.CHART_PLUS,
        "chart_star":           MSO_SHAPE.CHART_STAR,
        "chart_x":              MSO_SHAPE.CHART_X,
        "diagonal_stripe":      MSO_SHAPE.DIAGONAL_STRIPE,
        "line_inverse":         MSO_SHAPE.LINE_INVERSE,
    },
}

# ── ALL shape_keys as a flat set for validation ──
ALL_SHAPE_KEYS: frozenset[str] = frozenset(
    key for group in SHAPE_GROUPS.values() for key in group
)

# ── Reverse mapping: MSO_SHAPE → shape_key ──
SHAPE_KEY_BY_MSO: dict[MSO_SHAPE, str] = {
    mso: key
    for group in SHAPE_GROUPS.values()
    for key, mso in group.items()
}

# ── Reverse flat mapping for parser use ──
_SHAPE_MAP: dict[str, MSO_SHAPE] = {
    key: mso for group in SHAPE_GROUPS.values() for key, mso in group.items()
}


def resolve_shape(shape_key: str) -> MSO_SHAPE | None:
    """Return MSO_SHAPE for a shape_key, or None if invalid."""
    return _SHAPE_MAP.get(shape_key)


def list_shape_keys(group: str | None = None) -> list[str]:
    """List all shape_keys, optionally filtered by group name."""
    if group:
        return list(SHAPE_GROUPS.get(group, {}).keys())
    return sorted(_SHAPE_MAP.keys())
