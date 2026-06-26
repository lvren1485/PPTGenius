"""Spatial quality checks for slide elements — warning-only, never blocking.

Unified entry: ``check_element(element, buffer) → str``  for per-element checks.
``check_plan_bounds(parts) → list[str]`` for plan-level spatial validation.
"""

from __future__ import annotations

# ── geometry helpers ──────────────────────────────────────────────────

def _rects_overlap(a: dict, b: dict) -> bool:
    """True if two rectangles (with left/top/width/height) overlap."""
    al, at, aw, ah = a.get("left", 0), a.get("top", 0), a.get("width", 0), (a.get("height") or 0)
    bl, bt, bw, bh = b.get("left", 0), b.get("top", 0), b.get("width", 0), (b.get("height") or 0)
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return False
    return not (al + aw <= bl or bl + bw <= al or at + ah <= bt or bt + bh <= at)


def _overlap_pct(a: dict, b: dict) -> int:
    """Overlap area as percentage of rect a."""
    al, at, aw, ah = a.get("left", 0), a.get("top", 0), a.get("width", 0), (a.get("height") or 0)
    bl, bt, bw, bh = b.get("left", 0), b.get("top", 0), b.get("width", 0), (b.get("height") or 0)
    if aw <= 0 or ah <= 0:
        return 0
    ow = max(0, min(al + aw, bl + bw) - max(al, bl))
    oh = max(0, min(at + ah, bt + bh) - max(at, bt))
    return int((ow * oh) / (aw * ah) * 100)


# ── per-element checks ────────────────────────────────────────────────

def _check_aspect_ratio(
    w: float, h: float, el_type: str,
    *, rows: int = 0, cols: int = 0,
    label: str = "",
) -> list[str]:
    """Check aspect ratio only (not minimum size).  Shared by element + plan checks.

    ``label`` is prepended for plan-level output (e.g. the part name).
    """
    prefix = f"{label}: " if label else ""
    warnings: list[str] = []

    if el_type == "table":
        if rows > 0 and h / rows < 0.25:
            warnings.append(f"{prefix}表格每行仅 {h/rows:.2f}\"，可能无法阅读")
        if cols > 0 and w / cols < 0.6:
            warnings.append(f"{prefix}表格每列仅 {w/cols:.2f}\"，可能过窄")
        if h > 0 and (w / h > 5.0):
            warnings.append(f"{prefix}表格宽高比 {w/h:.1f}:1，过于扁平")
        if h > 0 and (w / h < 0.3):
            warnings.append(f"{prefix}表格宽高比 {w/h:.1f}:1，过于细长")
    elif el_type == "chart":
        if h > 0 and (w / h > 3.5):
            warnings.append(f"{prefix}图表宽高比 {w/h:.1f}:1，过于扁平")
        if h > 0 and (w / h < 0.5):
            warnings.append(f"{prefix}图表宽高比 {w/h:.1f}:1，过于细长")
    elif el_type == "picture":
        if h > 0 and (w / h > 5.0):
            warnings.append(f"{prefix}图片宽高比 {w/h:.1f}:1，过于扁平")
        if h > 0 and (w / h < 0.2):
            warnings.append(f"{prefix}图片宽高比 {w/h:.1f}:1，过于细长")

    return warnings


def _check_min_size(element: dict) -> list[str]:
    """Return warnings if element is unreasonably small / bad aspect ratio."""
    pos = element.get("position", {})
    w = pos.get("width", 0)
    h = pos.get("height") or 0
    el_type = element.get("type", "")
    warnings: list[str] = []

    # Element-level minimum sizes
    if el_type == "table":
        pass  # row/col handled by aspect ratio check
    elif el_type == "chart":
        if w < 1.5 or h < 1.5:
            warnings.append("图表尺寸过小（建议 ≥1.5×1.5 英寸），增大 width/height")
    elif el_type == "textbox":
        font_sizes: list[int] = []
        for block in element.get("content", []):
            for run in block.get("paragraph", {}).get("runs", []):
                fs = run.get("font", {}).get("size", 0)
                if fs:
                    font_sizes.append(fs)
        min_fs = min(font_sizes) if font_sizes else 14
        if h < min_fs / 72 * 1.5:
            warnings.append(f"文本框高度 {h:.2f}\" 不足以容纳一行 {min_fs}pt 文字")
    elif el_type == "picture":
        if w < 0.3 or (h and h < 0.3):
            warnings.append("图片尺寸过小（建议 ≥0.3 英寸），增大 width/height")

    if w < 0.5:
        warnings.append(f"元素宽度仅 {w:.2f}\"，可能过小")
    if h < 0.2:
        warnings.append(f"元素高度仅 {h:.2f}\"，可能过小")

    # Aspect ratio (shared)
    warnings.extend(_check_aspect_ratio(
        w, h, el_type,
        rows=element.get("rows", 0),
        cols=element.get("cols", 0),
    ))

    return warnings


def _check_text_overflow(element: dict, warnings: list[str]) -> None:
    """Rough estimate: will text fit inside the textbox?  Appends to warnings."""
    pos = element.get("position", {})
    w = pos.get("width", 0)
    h = pos.get("height") or 0
    if w <= 0 or h <= 0:
        return

    total_chars = 0
    max_font_size = 0
    for block in element.get("content", []):
        for run in block.get("paragraph", {}).get("runs", []):
            total_chars += len(run.get("text", ""))
            fs = run.get("font", {}).get("size", 0)
            if fs > max_font_size:
                max_font_size = fs

    if total_chars == 0 or max_font_size == 0:
        return

    font_w = max_font_size * 0.8
    line_h = max_font_size * 1.3
    chars_per_line = (w * 72) / font_w
    max_lines = (h * 72) / line_h
    capacity = chars_per_line * max_lines

    if total_chars > capacity * 1.5:
        warnings.append(
            f"文字可能溢出: 约 {total_chars} 字符, 文本框容量约 {int(capacity)} 字符 "
            f"(font={max_font_size}pt, box={w:.1f}×{h:.1f}\")"
        )


def _calc_layer_area(buffer: dict, z_order: int) -> int:
    """Percentage of slide area used by elements in the same z_order layer (±10)."""
    slide_area = 13.333 * 7.5
    used = 0.0
    for el in buffer.get("elements", {}).values():
        pos = el.get("position", {})
        ez = pos.get("z_order", 50)
        if abs(z_order - ez) <= 10:
            used += pos.get("width", 0) * (pos.get("height") or 0)
    return int(used / slide_area * 100)


# ── unified entry points ──────────────────────────────────────────────

def check_element(element: dict, buffer: dict) -> str:
    """Run all spatial checks on a single element before adding to buffer.

    Returns a warning string (possibly multi-line, ⚠-prefixed) or empty
    string if no issues.  Never raises — warnings are advisory only.
    """
    pos = element.get("position", {})
    if not pos:
        return ""
    new_z = pos.get("z_order", 50)
    el_type = element.get("type", "")
    warnings: list[str] = []

    # overlap with same-layer elements
    for eid, ex in buffer.get("elements", {}).items():
        ex_pos = ex.get("position", {})
        ex_z = ex_pos.get("z_order", 50)
        if abs(new_z - ex_z) <= 10 and _rects_overlap(pos, ex_pos):
            pct = _overlap_pct(pos, ex_pos)
            warnings.append(f"与元素 {eid} (z={ex_z}) 重叠 {pct}%，建议调整位置或 z_order")

    # text overflow
    if el_type == "textbox":
        _check_text_overflow(element, warnings)

    # minimum size
    warnings.extend(_check_min_size(element))

    # layer area usage
    layer_used = _calc_layer_area(buffer, new_z)
    if layer_used > 85:
        warnings.append(f"当前层 (z≈{new_z}) 已使用 {layer_used}%，空间紧张")
    elif layer_used > 70:
        warnings.append(f"当前层 (z≈{new_z}) 已使用 {layer_used}%")

    if not warnings:
        return ""
    return "\n".join(f"⚠ {w}" for w in warnings)


def check_plan_bounds(parts: dict) -> list[str]:
    """Check part bounds for overlaps, canvas overflow, type minimums, total area.

    Returns warning strings (empty list if all clear).
    """
    pw: list[str] = []
    parts_wb = [(name, info) for name, info in parts.items() if info.get("bounds")]
    if not parts_wb:
        return pw

    # part overlaps
    for i in range(len(parts_wb)):
        for j in range(i + 1, len(parts_wb)):
            a_name, a_info = parts_wb[i]
            b_name, b_info = parts_wb[j]
            if _rects_overlap(a_info["bounds"], b_info["bounds"]):
                pw.append(f"'{a_name}' 与 '{b_name}' 空间重叠，请调整 bounds")

    # canvas overflow
    for name, info in parts_wb:
        b = info["bounds"]
        w, h = b.get("width", 0), b.get("height", 0)
        if b.get("left", 0) + w > 13.333 or b.get("top", 0) + h > 7.5:
            pw.append(f"'{name}' 超出画布范围")

    # type-specific size + ratio (shared with _check_min_size)
    for name, info in parts_wb:
        b = info["bounds"]
        w, h = b.get("width", 0), b.get("height", 0)
        # Plan-level minimums — more conservative than element-level because bounds are estimates
        if info.get("has_chart") and (w < 2.0 or h < 2.0):
            pw.append(f"{name}: 图表建议 ≥2×2 英寸，当前 {w:.1f}×{h:.1f}")
        if info.get("has_table") and (w < 3.0 or h < 1.5):
            pw.append(f"{name}: 表格建议 ≥3×1.5 英寸，当前 {w:.1f}×{h:.1f}")
        if info.get("has_image") and (w < 0.5 or h < 0.5):
            pw.append(f"{name}: 图片建议 ≥0.5×0.5 英寸，当前 {w:.1f}×{h:.1f}")
        # Aspect ratio checks (shared)
        for el_type, flag in [("chart", "has_chart"), ("table", "has_table"), ("picture", "has_image")]:
            if info.get(flag):
                pw.extend(_check_aspect_ratio(w, h, el_type, label=name))

    # total area
    total = sum(
        info["bounds"].get("width", 0) * info["bounds"].get("height", 0)
        for _, info in parts_wb
    )
    canvas = 13.333 * 7.5
    if total > canvas * 0.75:
        pw.append(f"规划总面积 {total:.0f} sq in（画布 {canvas:.0f}），超出 75%，建议削减 part 数量")

    return pw
