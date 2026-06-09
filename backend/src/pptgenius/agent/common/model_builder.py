"""Unified LLM builder — creates ChatOpenAI + middleware + agent_id for every sub-agent."""

from __future__ import annotations

import secrets

from langchain_openai import ChatOpenAI

from pptgenius.agent.common.langchain_adapter import apply_deepseek_patch
from pptgenius.infrastructure.config.settings import get_settings
from pptgenius.infrastructure.utils import get_logger

from .token_middleware import TokenCountingMiddleware

_log = get_logger("pptgenius.agent.common.model_builder")
apply_deepseek_patch()


def build_llm(
    conversation_id: int,
    *,
    on_tokens=None,
) -> tuple[ChatOpenAI, str, TokenCountingMiddleware]:
    """Create a ChatOpenAI instance with token-counting middleware.

    Returns (llm, agent_id, middleware).  Caller can pass middleware to
    ``create_agent(..., middleware=[middleware])``.
    """
    settings = get_settings()
    agent_id = secrets.token_hex(4)

    llm = ChatOpenAI(
        model=settings.llm.model,
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
    )

    middleware = TokenCountingMiddleware(
        conversation_id=conversation_id,
        agent_id=agent_id,
        on_tokens=on_tokens,
    )

    _log.debug("built llm conv=%d agent=%s model=%s", conversation_id, agent_id, settings.llm.model)
    return llm, agent_id, middleware
