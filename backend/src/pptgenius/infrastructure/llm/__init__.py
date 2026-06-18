"""LLM infrastructure — adapter patches + factory for ChatOpenAI + agent_id."""

from pptgenius.infrastructure.llm.adapter import apply_deepseek_patch, is_patched
from pptgenius.infrastructure.llm.factory import create_llm

__all__ = ["apply_deepseek_patch", "create_llm", "is_patched"]
