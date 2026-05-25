"""ppt_engine parser — Pydantic models, validator, and renderers.

Usage:
    from ppt_engine.parser import validate_instruction, PPTInstruction, ValidationResult

    result = validate_instruction(instruction_dict)
    if result.is_valid:
        instruction = result.parsed
"""

from .base import PPTInstruction

__all__ = ["PPTInstruction"]
