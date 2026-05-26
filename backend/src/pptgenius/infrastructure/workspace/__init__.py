"""Workspace — per-conversation directory manager (singleton).

Usage::

    from pptgenius.infrastructure.workspace import WorkspaceManager

    wm = WorkspaceManager()
    wm.create(conv_id)          # create directories
    path = wm.get_input_dir(conv_id)
    path = wm.get_knowledge_dir(conv_id)
    path = wm.get_output_dir(conv_id)
"""

from .manager import WorkspaceManager

__all__ = [
    "WorkspaceManager",
]
