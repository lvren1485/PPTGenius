"""PPT agent — two-phase pipeline (Style → Per-Slide → Assembly).

Mode: super_freedom — one agent with full creative control per slide,
no template enforcement, complete slide instruction per slide.
"""

from .graph import build_ppt_graph

__all__ = ["build_ppt_graph"]
