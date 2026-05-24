"""LLM token usage accumulator — per-conversation, with DeepSeek cache pricing.

Compatible with:
- raw DeepSeek API ``usage`` dict
- LangChain ``AIMessage.usage_metadata``
- LangChain ``UsageMetadataCallbackHandler`` output
"""

from __future__ import annotations

from .logger import get_logger

# DeepSeek official pricing (CNY per 1M tokens) — 2025-06
_PRICING: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {
        "cache_hit":  0.02,
        "cache_miss": 1.00,
        "output":     2.00,
    },
    "deepseek-v4-pro": {
        "cache_hit":  0.025,
        "cache_miss": 3.00,
        "output":     6.00,
    },
}
_FALLBACK_MODEL = "deepseek-v4-flash"

# Usage field aliases (raw DeepSeek → LangChain UsageMetadata)
_PROMPT_KEYS = ("prompt_tokens", "input_tokens")
_COMPLETION_KEYS = ("completion_tokens", "output_tokens")
_TOTAL_KEYS = ("total_tokens",)


def _first_of(d: dict, *keys: str, default: int = 0) -> int:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


# -- per-conversation registry -----------------------------------------------

_counters: dict[int, "TokenCounter"] = {}


class TokenCounter:
    """Accumulate token usage for one conversation.

    Usage with LangGraph / LangChain::

        # In a model node:
        response = await llm.ainvoke(messages)
        tc = TokenCounter.for_conversation(conversation_id)
        tc.add(response.usage_metadata)

        # Later:
        print(tc.snapshot())
    """

    def __init__(self, model_name: str = "deepseek-v4-flash") -> None:
        self.model_name = model_name
        self._log = get_logger("pptgenius.token")
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._cache_hit_tokens = 0
        self._cache_miss_tokens = 0
        self._reasoning_tokens = 0
        self._call_count = 0

    # -- registry ------------------------------------------------------------

    @classmethod
    def for_conversation(cls, conversation_id: int, model_name: str = "deepseek-v4-flash") -> "TokenCounter":
        """Get or create the TokenCounter for *conversation_id*."""
        tc = _counters.get(conversation_id)
        if tc is None:
            tc = _counters[conversation_id] = cls(model_name)
        return tc

    @classmethod
    def get(cls, conversation_id: int) -> "TokenCounter | None":
        """Return the TokenCounter for *conversation_id* or None."""
        return _counters.get(conversation_id)

    @classmethod
    def remove(cls, conversation_id: int) -> None:
        """Discard the counter for *conversation_id*."""
        _counters.pop(conversation_id, None)

    # -- public API ----------------------------------------------------------

    def add(self, usage: dict | None) -> "TokenCounter":
        """Accumulate *usage* dict from LLM response. Returns self for chaining."""
        if not usage:
            return self

        prompt = _first_of(usage, *_PROMPT_KEYS)
        completion = _first_of(usage, *_COMPLETION_KEYS)
        total = _first_of(usage, *_TOTAL_KEYS, default=prompt + completion)

        input_details = usage.get("input_token_details") or usage.get("prompt_tokens_details") or {}
        output_details = usage.get("output_token_details") or usage.get("completion_tokens_details") or {}

        # DeepSeek top-level cache fields (prompt_cache_hit + prompt_cache_miss = prompt_tokens)
        cache_hit = usage.get("prompt_cache_hit_tokens", 0)
        cache_miss = usage.get("prompt_cache_miss_tokens", 0)
        # Fallback: nested cached_tokens / cache_read
        if cache_hit == 0 and cache_miss == 0:
            nested_cached = input_details.get("cached_tokens", 0) or input_details.get("cache_read", 0)
            if nested_cached:
                cache_hit = nested_cached
                cache_miss = prompt - nested_cached
            else:
                cache_miss = prompt

        reasoning = output_details.get("reasoning_tokens", 0) or output_details.get("reasoning", 0)

        self._prompt_tokens += prompt
        self._completion_tokens += completion
        self._total_tokens += total
        self._cache_hit_tokens += cache_hit
        self._cache_miss_tokens += cache_miss
        self._reasoning_tokens += reasoning
        self._call_count += 1

        self._log.debug(
            "call #%d  prompt=%-5d (hit=%d miss=%d)  completion=%-5d (reasoning=%d)  total=%d",
            self._call_count, prompt, cache_hit, cache_miss, completion, reasoning, total,
        )
        return self

    def estimate_cost(self) -> float:
        """Estimated cost in CNY using cache-aware DeepSeek pricing."""
        p = _PRICING.get(self.model_name, _PRICING[_FALLBACK_MODEL])
        return (
            self._cache_hit_tokens * p["cache_hit"]
            + self._cache_miss_tokens * p["cache_miss"]
            + self._completion_tokens * p["output"]
        ) / 1_000_000

    def snapshot(self) -> dict:
        """Return a summary dict of accumulated usage."""
        return {
            "model": self.model_name,
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "total_tokens": self._total_tokens,
            "cache_hit_tokens": self._cache_hit_tokens,
            "cache_miss_tokens": self._cache_miss_tokens,
            "reasoning_tokens": self._reasoning_tokens,
            "call_count": self._call_count,
            "estimated_cost_cny": round(self.estimate_cost(), 6),
        }

    def reset(self) -> None:
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._cache_hit_tokens = 0
        self._cache_miss_tokens = 0
        self._reasoning_tokens = 0
        self._call_count = 0

    # -- properties ----------------------------------------------------------

    @property
    def prompt_tokens(self) -> int:
        return self._prompt_tokens

    @property
    def completion_tokens(self) -> int:
        return self._completion_tokens

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def cache_hit_tokens(self) -> int:
        return self._cache_hit_tokens

    @property
    def cache_miss_tokens(self) -> int:
        return self._cache_miss_tokens

    @property
    def reasoning_tokens(self) -> int:
        return self._reasoning_tokens

    @property
    def call_count(self) -> int:
        return self._call_count
