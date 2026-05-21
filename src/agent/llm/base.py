from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class LLMClient(ABC):
    """Abstract base for LLM API clients."""

    @abstractmethod
    def chat(
        self,
        system: str | None = None,
        messages: list[LLMMessage | str] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            system: Optional system prompt.
            messages: List of messages (LLMMessage objects or plain strings).
            model: Model override (uses default if None).
        Returns:
            LLMResponse with full text content.
        """
        ...

    @abstractmethod
    def chat_structured(
        self,
        response_model: type[T],
        system: str | None = None,
        messages: list[LLMMessage | str] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> tuple[T, LLMResponse]:
        """Request a structured (typed) response from the LLM.

        Returns:
            Tuple of (parsed_model, raw_LLMResponse).
        """
        ...


class MockLLMClient(LLMClient):
    """Mock client for development without an API key.

    Returns canned responses for testing the pipeline.
    """

    def chat(
        self,
        system: str | None = None,
        messages: list[LLMMessage | str] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        return LLMResponse(
            text="[Mock LLM response]",
            model=model or "mock",
        )

    def chat_structured(
        self,
        response_model: type[T],
        system: str | None = None,
        messages: list[LLMMessage | str] | None = None,
        model: str | None = None,
        **kwargs,
    ) -> tuple[T, LLMResponse]:
        # Return an empty/default instance of the model
        try:
            instance = response_model()
        except TypeError:
            instance = response_model(**{})
        return instance, LLMResponse(
            text="[Mock structured response]",
            model=model or "mock",
        )
