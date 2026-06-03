"""DEPRECATED — re-exports from the neutral ppt/dispatcher.py location.

The dispatcher was moved out of phase2_sub_agent since it now only
invokes super_freedom.  Import from pptgenius.agent.ppt.dispatcher instead.
"""

from ..dispatcher import (  # noqa: F401
    _MAX_CONCURRENT_SLIDES,
    _build_neighbor_context,
    _process_super_freedom_slide,
    dispatcher_node,
)
