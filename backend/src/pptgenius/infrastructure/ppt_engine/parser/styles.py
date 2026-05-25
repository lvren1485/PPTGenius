"""Safe, wrapped lxml operations for python-pptx.

LLM agents MUST use these functions; they MUST NOT construct lxml/XML directly.
Every function accepts plain Python values (str, int, float) and handles the
lxml details internally.

Categories:
  Text effects — strikethrough, small caps, all caps, kerning, text glow, text outline
  Shape fills — picture fill on shapes, radial gradient, multi-stop gradient
  Table —— cell borders, cell fill + border combined
  Chart —– chart area fill, plot area fill
  Backgrounds — slide image background
"""

from __future__ import annotations

from lxml import etree
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt


# ═══════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════

def _SubElement(parent: etree._Element, tag: str, **attrib) -> etree._Element:
    """Create a sub-element with string attributes."""
    elm = OxmlElement(tag)
    for k, v in attrib.items():
        elm.set(k, str(v))
    parent.append(elm)
    return elm


def _hex_to_rgb(hex_color: str) -> RGBColor:
    """Convert '#1a73e8' or '1a73e8' to RGBColor, or raise ValueError."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    return RGBColor.from_string(h)


# ═══════════════════════════════════════════════════════════════════
# TEXT EFFECTS
# ═══════════════════════════════════════════════════════════════════

def set_text_strikethrough(run, style: str = "sngStrike") -> None:
    """Apply strikethrough to a Run.

    Args:
        run: python-pptx _Run object.
        style: 'sngStrike' (single) or 'dblStrike' (double).
    """
    rPr = run._r.get_or_add_rPr()
    rPr.set("strike", style)


def set_text_small_caps(run) -> None:
    """Apply small caps to a Run."""
    rPr = run._r.get_or_add_rPr()
    rPr.set("cap", "small")


def set_text_all_caps(run) -> None:
    """Apply all caps to a Run."""
    rPr = run._r.get_or_add_rPr()
    rPr.set("cap", "all")


def set_text_kerning(run, font_size_pt: float, kern_pt: float | None = None) -> None:
    """Set kerning on a Run.

    Args:
        run: python-pptx _Run.
        font_size_pt: font size in points (used to compute EMU).
        kern_pt: kerning amount in points. If None, defaults to font_size_pt.
    """
    rPr = run._r.get_or_add_rPr()
    if kern_pt is None:
        kern_pt = font_size_pt
    rPr.set("kern", str(int(Pt(kern_pt))))


def set_text_shadow(
    run,
    blur_pt: float = 3.0,
    offset_pt: float = 1.5,
    angle_deg: float = 315.0,
    color_hex: str = "000000",
    alpha_pct: float = 40.0,
) -> None:
    """Add an outer shadow to a Run.

    Args:
        run: python-pptx _Run.
        blur_pt: blur radius in points.
        offset_pt: shadow offset distance.
        angle_deg: angle of shadow in degrees (0=right, 90=up, 180=left, 270=down).
        color_hex: hex color without #.
        alpha_pct: alpha/opacity 0-100 (100=fully opaque).
    """
    rPr = run._r.get_or_add_rPr()
    effectLst = etree.SubElement(rPr, qn("a:effectLst"))
    outerShdw = etree.SubElement(effectLst, qn("a:outerShdw"))
    outerShdw.set("blurRad", str(int(Pt(blur_pt))))
    outerShdw.set("dist", str(int(Pt(offset_pt))))
    outerShdw.set("dir", str(int(angle_deg * 60000)))

    srgbClr = etree.SubElement(outerShdw, qn("a:srgbClr"))
    srgbClr.set("val", color_hex)
    alpha_el = etree.SubElement(srgbClr, qn("a:alpha"))
    alpha_el.set("val", str(int(alpha_pct * 1000)))  # 0–100000


def set_text_glow(
    run,
    radius_pt: float = 8.0,
    color_hex: str = "1a73e8",
    alpha_pct: float = 60.0,
) -> None:
    """Add a glow effect to a Run."""
    rPr = run._r.get_or_add_rPr()
    effectLst = etree.SubElement(rPr, qn("a:effectLst"))
    glow = etree.SubElement(effectLst, qn("a:glow"))
    glow.set("rad", str(int(Pt(radius_pt))))

    srgbClr = etree.SubElement(glow, qn("a:srgbClr"))
    srgbClr.set("val", color_hex)
    alpha_el = etree.SubElement(srgbClr, qn("a:alpha"))
    alpha_el.set("val", str(int(alpha_pct * 1000)))


# ═══════════════════════════════════════════════════════════════════
# SHAPE FILLS
# ═══════════════════════════════════════════════════════════════════

def set_shape_picture_fill(shape, image_path: str, fill_mode: str = "stretch") -> None:
    """Fill a shape with a picture (stretch or tile).

    Args:
        shape: python-pptx shape (AutoShape).
        image_path: absolute path to image file.
        fill_mode: 'stretch' or 'tile'.
    """
    rId = shape.part.relate_to(
        image_path,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
    )

    spPr = shape._element.spPr
    # Remove existing fills
    to_remove = []
    for child in spPr:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag in ("solidFill", "gradFill", "pattFill", "noFill"):
            to_remove.append(child)
    for child in to_remove:
        spPr.remove(child)

    if fill_mode == "stretch":
        fill_mode_fragment = "<a:stretch><a:fillRect/></a:stretch>"
    else:
        fill_mode_fragment = "<a:tile/>"

    blipFill = etree.fromstring(
        f'<a:blipFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        f' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<a:blip r:embed="{rId}"/>{fill_mode_fragment}</a:blipFill>'
    )
    spPr.append(blipFill)


def add_gradient_stop(shape, position: float, color_hex: str) -> None:
    """Add an extra gradient stop to a shape's gradient fill.

    Args:
        shape: python-pptx shape with gradient fill already applied.
        position: 0.0–1.0 position along the gradient.
        color_hex: hex color without #.
    """
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls

    pos_val = str(int(position * 100000))
    new_gs = parse_xml(
        f'<a:gs pos="{pos_val}" {nsdecls("a")}>\n'
        f'  <a:srgbClr val="{color_hex}"/>\n'
        f"</a:gs>"
    )
    gsLst = shape.fill.gradient_stops._gsLst
    # Insert keeping ascending order
    insert_pos = 0
    for i, child in enumerate(gsLst):
        existing_pos = int(child.get("pos", "0"))
        if existing_pos < int(pos_val):
            insert_pos = i + 1
        else:
            break
    gsLst.insert(insert_pos, new_gs)


# ═══════════════════════════════════════════════════════════════════
# TABLE
# ═══════════════════════════════════════════════════════════════════

def set_cell_border(
    cell,
    color_hex: str = "333333",
    width_pt: float = 1.0,
    edges: tuple[str, ...] = ("left", "right", "top", "bottom"),
) -> None:
    """Set border on a table cell.

    Args:
        cell: python-pptx _Cell.
        color_hex: border color without #.
        width_pt: border width in points.
        edges: which edges to apply ('left','right','top','bottom').
    """
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    edge_tags = {
        "left": "a:lnL", "right": "a:lnR", "top": "a:lnT", "bottom": "a:lnB",
    }
    width_emu = str(int(Pt(width_pt)))

    for edge in edges:
        tag = edge_tags[edge]
        ln = OxmlElement(tag)
        ln.set("w", width_emu)
        ln.set("cap", "flat")
        ln.set("cmpd", "sng")
        ln.set("algn", "ctr")
        sf = OxmlElement("a:solidFill")
        sc = OxmlElement("a:srgbClr")
        sc.set("val", color_hex)
        sf.append(sc)
        ln.append(sf)
        _SubElement(ln, "a:prstDash", val="solid")
        _SubElement(ln, "a:round")
        _SubElement(ln, "a:headEnd", type="none", w="med", len="med")
        _SubElement(ln, "a:tailEnd", type="none", w="med", len="med")
        tcPr.append(ln)


def set_cell_fill_and_border(
    cell,
    fill_hex: str | None = None,
    border_hex: str = "e0e0e0",
    border_width_pt: float = 0.5,
) -> None:
    """Combined cell fill + border in one operation.

    Uses theme-based approach for correct coexistence of fill and borders.
    """
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()

    # Borders (all 4 edges)
    width_emu = str(int(Pt(border_width_pt)))
    for ln_tag in ["a:lnL", "a:lnR", "a:lnT", "a:lnB"]:
        ln = OxmlElement(ln_tag)
        ln.set("w", width_emu)
        ln.set("cap", "flat")
        ln.set("cmpd", "sng")
        ln.set("algn", "ctr")
        sf = OxmlElement("a:solidFill")
        sc = OxmlElement("a:srgbClr")
        sc.set("val", border_hex)
        sf.append(sc)
        ln.append(sf)
        _SubElement(ln, "a:prstDash", val="solid")
        _SubElement(ln, "a:round")
        _SubElement(ln, "a:headEnd", type="none", w="med", len="med")
        _SubElement(ln, "a:tailEnd", type="none", w="med", len="med")
        tcPr.append(ln)

    # Fill via high-level API (preferred when possible)
    if fill_hex:
        cell.fill.solid()
        cell.fill.fore_color.rgb = _hex_to_rgb(fill_hex)


# ═══════════════════════════════════════════════════════════════════
# CHART AREA / PLOT AREA
# ═══════════════════════════════════════════════════════════════════

def set_chart_area_fill(chart, color_hex: str | None = None, no_fill: bool = False) -> None:
    """Set chart area (outer) background fill.

    Args:
        chart: python-pptx Chart object.
        color_hex: fill color without #, or None for no color.
        no_fill: if True, set transparent (overrides color_hex).
    """
    spPr = OxmlElement("c:spPr")
    if no_fill:
        spPr.append(OxmlElement("a:noFill"))
    elif color_hex:
        sf = OxmlElement("a:solidFill")
        sc = OxmlElement("a:srgbClr")
        sc.set("val", color_hex)
        sf.append(sc)
        spPr.append(sf)
    else:
        return  # nothing to do
    chart._element.append(spPr)


def set_plot_area_fill(chart, color_hex: str | None = None, no_fill: bool = False) -> None:
    """Set plot area (inner) background fill."""
    plot_area = chart._element.chart.plotArea
    spPr = OxmlElement("c:spPr")
    if no_fill:
        spPr.append(OxmlElement("a:noFill"))
    elif color_hex:
        sf = OxmlElement("a:solidFill")
        sc = OxmlElement("a:srgbClr")
        sc.set("val", color_hex)
        sf.append(sc)
        spPr.append(sf)
    else:
        return
    plot_area.append(spPr)


# ═══════════════════════════════════════════════════════════════════
# SLIDE BACKGROUNDS
# ═══════════════════════════════════════════════════════════════════

def set_slide_image_background(slide, image_path: str, fill_mode: str = "stretch") -> None:
    """Set slide background to an image (true background, not overlay shape).

    Args:
        slide: python-pptx Slide.
        image_path: absolute path to image file.
        fill_mode: 'stretch' or 'tile'.
    """
    rId = slide.part.relate_to(
        image_path,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
    )

    bg = slide.background._element
    bgPr = bg.find(qn("p:bgPr"))
    if bgPr is None:
        bgPr = OxmlElement("p:bgPr")
        bg.insert(0, bgPr)
    else:
        for child in list(bgPr):
            bgPr.remove(child)

    if fill_mode == "stretch":
        fill_mode_fragment = "<a:stretch><a:fillRect/></a:stretch>"
    else:
        fill_mode_fragment = "<a:tile/>"

    blipFill = etree.fromstring(
        f'<p:blipFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        f' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        f' xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        f'<a:blip r:embed="{rId}"/>{fill_mode_fragment}</p:blipFill>'
    )
    bgPr.append(blipFill)


# ═══════════════════════════════════════════════════════════════════
# Shape solid fill helpers (convenience wrappers, not lxml)
# ═══════════════════════════════════════════════════════════════════

def apply_shape_fill(shape, fill_type: str, color_hex: str | None = None) -> None:
    """Apply a fill to a shape.

    Args:
        shape: python-pptx Shape.
        fill_type: 'solid', 'no_fill', 'gradient'.
        color_hex: for 'solid', the fill color without #.
    """
    if fill_type == "no_fill":
        shape.fill.background()
    elif fill_type == "solid" and color_hex:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _hex_to_rgb(color_hex)
    elif fill_type == "gradient":
        shape.fill.gradient()


def apply_shape_line(
    shape,
    color_hex: str | None = None,
    width_pt: float = 1.0,
    dash_style: str | None = None,
) -> None:
    """Apply line formatting to a shape.

    Args:
        shape: python-pptx Shape.
        color_hex: line color without #, or None for no line.
        width_pt: line width in points.
        dash_style: 'solid', 'dash', 'dot', 'dash_dot', or None.
    """
    from pptx.enum.dml import MSO_LINE_DASH_STYLE

    if color_hex is None:
        shape.line.fill.background()
        return
    shape.line.color.rgb = _hex_to_rgb(color_hex)
    shape.line.width = Pt(width_pt)
    if dash_style:
        dash_map = {
            "solid": MSO_LINE_DASH_STYLE.SOLID,
            "dash": MSO_LINE_DASH_STYLE.DASH,
            "dot": MSO_LINE_DASH_STYLE.SYS_DOT,
            "dash_dot": MSO_LINE_DASH_STYLE.DASH_DOT,
        }
        if style := dash_map.get(dash_style):
            shape.line.dash_style = style
