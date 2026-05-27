"""ppt_engine — python-pptx PPT generation layer.

Package-level entry points:
    from pptgenius.infrastructure.ppt_engine import (
        validate_instruction,   # validate full PPTInstruction JSON
        validate_elements,      # validate flat list of element dicts
        generate_ppt,           # validate + build .pptx
        search_icons,           # search bundled Tabler icons by tag
    )
"""

from .validator import validate_instruction, validate_elements, ValidationResult
from .generator import generate_ppt
from .icon_search import search_icons

__all__ = [
    "validate_instruction",
    "validate_elements",
    "ValidationResult",
    "generate_ppt",
    "search_icons",
]
