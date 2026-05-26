"""Image element renderer. SVG auto-converted via cairosvg when available."""

import logging
import os

from pptx.util import Inches

from .base import ImageElement

logger = logging.getLogger("ppt_engine.image")


def render_picture(slide, el: ImageElement, workspace_path: str = ".") -> None:
    """Render a picture element onto a slide."""
    left = Inches(el.position.left)
    top = Inches(el.position.top)

    img_path = el.path
    if not os.path.isabs(img_path):
        img_path = os.path.join(workspace_path, img_path)

    if not os.path.exists(img_path):
        logger.error("Image not found: %s", img_path)
        raise FileNotFoundError(f"Image not found: {img_path}")

    # SVG → PNG conversion (best-effort)
    if img_path.lower().endswith(".svg"):
        img_path = _svg_to_png(img_path)

    if el.fit == "aspect":
        width = Inches(el.position.width)
        if el.position.height is not None:
            slide.shapes.add_picture(img_path, left, top, width, Inches(el.position.height))
        else:
            slide.shapes.add_picture(img_path, left, top, width)
    else:
        width = Inches(el.position.width)
        height = Inches(el.position.height) if el.position.height else width
        slide.shapes.add_picture(img_path, left, top, width, height)


def _svg_to_png(svg_path: str) -> str:
    """Convert SVG to PNG via cairosvg. Falls back to skip if unavailable."""
    png_path = svg_path.rsplit(".", 1)[0] + ".png"
    if os.path.exists(png_path) and os.path.getmtime(png_path) >= os.path.getmtime(svg_path):
        return png_path

    try:
        import cairosvg
        cairosvg.svg2png(url=svg_path, write_to=png_path, dpi=300)
        logger.info("SVG converted: %s → %s", svg_path, png_path)
        return png_path
    except ImportError:
        logger.warning("cairosvg not installed, using SVG directly (may fail)")
        return svg_path
    except OSError as e:
        logger.warning("cairosvg/Cairo unavailable (%s), using SVG directly", e)
        return svg_path
