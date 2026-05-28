"""PPT agent — two-phase pipeline (Style → Per-Slide → Assembly).

Two modes (code-isolated):
  - sub_agent: Supervisor dispatches TextAgent + ChartAgent + ShapeAgent per slide
  - freedom:   One FreedomAgent generates all elements at once per slide
"""

from .graph import build_ppt_graph

__all__ = ["build_ppt_graph"]
