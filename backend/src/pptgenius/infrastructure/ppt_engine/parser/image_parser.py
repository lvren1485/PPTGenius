"""Image element renderer. SVG auto-converted to PNG before embedding.

Primary: resvg-py (Rust, pre-built wheels for all platforms, no system deps).
Fallback: cairosvg (needs Cairo lib: apt install libcairo2 on Linux).
"""

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
    """Convert SVG to PNG at 300 DPI. Resvg primary, cairosvg fallback."""
    png_path = svg_path.rsplit(".", 1)[0] + ".png"

    # Cache: skip re-conversion if PNG is newer than SVG source
    if os.path.exists(png_path) and os.path.getmtime(png_path) >= os.path.getmtime(svg_path):
        return png_path

    # Primary: resvg-py (pre-built wheels, zero system deps)
    try:
        import resvg_py
        png_bytes = resvg_py.svg_to_bytes(svg_path=svg_path, dpi=300)
        with open(png_path, "wb") as f:
            f.write(png_bytes)
        logger.info("SVG → PNG (resvg, 300 DPI): %s", os.path.basename(svg_path))
        return png_path
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("resvg-py failed: %s, trying cairosvg fallback", exc)

    # Fallback: cairosvg (needs libcairo2 on Linux, GTK runtime on Windows)
    try:
        import cairosvg
        cairosvg.svg2png(url=svg_path, write_to=png_path, dpi=300)
        logger.info("SVG → PNG (cairosvg, 300 DPI): %s", os.path.basename(svg_path))
        return png_path
    except ImportError:
        logger.warning("No SVG converter available. Install resvg-py or cairosvg.")
        return svg_path
    except OSError as exc:
        logger.warning("Cairo library not found (%s). Install libcairo2 or use resvg-py.", exc)
        return svg_path
