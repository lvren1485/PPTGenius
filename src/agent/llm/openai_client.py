import json
from typing import Any, TypeVar

from openai import OpenAI

from .base import LLMClient, LLMResponse, LLMMessage
from ..config import config


T = TypeVar("T")


class OpenAIClient(LLMClient):
    """LLM client backed by the OpenAI API."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or config.OPENAI_API_KEY
        self.default_model = model or config.OPENAI_MODEL
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def _prepare_messages(
        self,
        system: str | None = None,
        messages: list[LLMMessage | str] | None = None,
    ) -> list[dict]:
        result = []
        if system:
            result.append({"role": "system", "content": system})
        if messages:
            for m in messages:
                if isinstance(m, str):
                    result.append({"role": "user", "content": m})
                else:
                    result.append(m.to_dict())
        return result

    def chat(
        self,
        system: str | None = None,
        messages: list[LLMMessage | str] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                text="[No API key configured]",
                model=model or self.default_model,
            )

        resp = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=self._prepare_messages(system, messages),
            **kwargs,
        )
        choice = resp.choices[0]
        usage = resp.usage
        return LLMResponse(
            text=choice.message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=resp.model,
        )

    def chat_structured(
        self,
        response_model: type[T],
        system: str | None = None,
        messages: list[LLMMessage | str] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> tuple[T, LLMResponse]:
        if not self.api_key:
            return response_model(), LLMResponse(
                text="[No API key configured]",
                model=model or self.default_model,
            )

        # Use OpenAI structured outputs via response_format
        resp = self.client.beta.chat.completions.parse(
            model=model or self.default_model,
            messages=self._prepare_messages(system, messages),
            response_format=response_model,
            **kwargs,
        )
        choice = resp.choices[0]
        parsed: T = choice.message.parsed
        usage = resp.usage
        raw = LLMResponse(
            text=choice.message.content or json.dumps(parsed, default=str),
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=resp.model,
        )
        return parsed, raw


def create_llm_client() -> LLMClient:
    """Factory: returns real client if API key is available, else mock."""
    if config.OPENAI_API_KEY:
        return OpenAIClient()
    from .base import MockLLMClient
    return MockLLMClient()
