"""Image element renderer.

SVG files are converted to PNG via cairosvg before insertion.
"""

import os
from io import BytesIO

from pptx.util import Inches

from .base import ImageElement


def render_picture(slide, el: ImageElement, workspace_path: str = ".") -> None:
    """Render a picture element onto a slide. SVG is auto-converted."""
    left = Inches(el.position.left)
    top = Inches(el.position.top)

    # Resolve path relative to workspace
    img_path = el.path
    if not os.path.isabs(img_path):
        img_path = os.path.join(workspace_path, img_path)

    # SVG → PNG conversion
    if img_path.lower().endswith(".svg"):
        img_path = _svg_to_png(img_path)

    if el.fit == "aspect":
        # Only width, auto-height
        width = Inches(el.position.width)
        if el.position.height is not None:
            pic = slide.shapes.add_picture(
                img_path, left, top, width, Inches(el.position.height)
            )
        else:
            pic = slide.shapes.add_picture(img_path, left, top, width)
    else:
        # stretch or crop → both dimensions
        width = Inches(el.position.width)
        height = Inches(el.position.height) if el.position.height else width
        pic = slide.shapes.add_picture(img_path, left, top, width, height)
        if el.fit == "crop":
            pic.crop_left = 0
            pic.crop_right = 0
            pic.crop_top = 0
            pic.crop_bottom = 0


def _svg_to_png(svg_path: str) -> str:
    """Convert SVG to PNG via cairosvg, return the PNG path."""
    import cairosvg

    png_path = svg_path.rsplit(".", 1)[0] + ".png"
    if os.path.exists(png_path) and os.path.getmtime(png_path) >= os.path.getmtime(svg_path):
        return png_path  # cached, no re-convert

    cairosvg.svg2png(url=svg_path, write_to=png_path, dpi=300)
    return png_path
