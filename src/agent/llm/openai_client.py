import json
from typing import Any, TypeVar

from openai import OpenAI

from .base import LLMClient, LLMResponse, LLMMessage
from ..config import config


T = TypeVar("T")


class OpenAIClient(LLMClient):
    """LLM client backed by any OpenAI-compatible API (OpenAI, DeepSeek, etc.)."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or config.OPENAI_API_KEY
        self.default_model = model or config.OPENAI_MODEL
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            kwargs = {"api_key": self.api_key}
            if config.OPENAI_BASE_URL:
                kwargs["base_url"] = config.OPENAI_BASE_URL
            self._client = OpenAI(**kwargs)
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

        # Remove kwargs not supported by all providers
        kwargs.pop("response_format", None)

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

        # Use standard chat API + JSON mode (compatible with DeepSeek)
        system_prompt = system or ""
        json_instruction = (
            "\n\nYou MUST respond with valid JSON matching this schema: "
            + json.dumps(response_model.model_json_schema(), ensure_ascii=False)
        )

        resp = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=self._prepare_messages(system_prompt + json_instruction, messages),
            response_format={"type": "json_object"},
            **{k: v for k, v in kwargs.items() if k != "response_format"},
        )
        choice = resp.choices[0]
        text = choice.message.content or "{}"
        usage = resp.usage

        try:
            parsed = response_model(**json.loads(text))
        except (json.JSONDecodeError, TypeError) as e:
            parsed = response_model()

        raw = LLMResponse(
            text=text,
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
