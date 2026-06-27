"""LLM factory — creates ChatOpenAI + generates agent_id.

``agent_id`` is a by-product of LLM construction.  Used as the key for
TokenCountingMiddleware and the push_agent / pop_agent registry.
"""

from __future__ import annotations

import secrets

from langchain_openai import ChatOpenAI

from pptgenius.infrastructure.config.settings import get_settings
from pptgenius.infrastructure.llm.adapter import apply_deepseek_patch
from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.infrastructure.llm.factory")
apply_deepseek_patch()


def create_llm(
    conversation_id: int,
) -> tuple[ChatOpenAI, str]:
    """Create a ChatOpenAI instance and generate an agent_id.

    Returns (llm, agent_id).  Use ``build_middlewares(conversation_id, agent_id)``
    from ``agent.common.middleware`` to construct the standard middleware list.
    """
    settings = get_settings()
    agent_id = secrets.token_hex(4)

    llm = ChatOpenAI(
        model=settings.llm.model,
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
        model_kwargs={"parallel_tool_calls": False},
    )

    _log.debug("built llm conv=%d agent=%s model=%s", conversation_id, agent_id, settings.llm.model)
    return llm, agent_id
