"""ppt_engine — python-pptx PPT generation layer.

Package-level entry points:
    from pptgenius.infrastructure.ppt_engine import (
        validate_instruction,   # validate full PPTInstruction JSON
        validate_elements,      # validate flat list of element dicts
        generate_ppt,           # validate + build .pptx
    )
"""

from .validator import validate_instruction, validate_elements, ValidationResult
from .generator import generate_ppt

__all__ = [
    "validate_instruction",
    "validate_elements",
    "ValidationResult",
    "generate_ppt",
]
