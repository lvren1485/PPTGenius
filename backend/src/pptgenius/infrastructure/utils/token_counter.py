"""LLM token usage accumulator — per-agent registry with DeepSeek cache pricing.

Conversation-level cost is tracked in the DB (conversations.estimated_cost),
not here.  This module only tracks per-agent token usage during a single
agent invocation — counters are removed after their results are persisted.
"""

from __future__ import annotations

from .logger import get_logger

_PRICING: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {"cache_hit": 0.02, "cache_miss": 1.00, "output": 2.00},
    "deepseek-v4-pro":  {"cache_hit": 0.025, "cache_miss": 3.00, "output": 6.00},
}
_FALLBACK_MODEL = "deepseek-v4-flash"

_PROMPT_KEYS = ("prompt_tokens", "input_tokens")
_COMPLETION_KEYS = ("completion_tokens", "output_tokens")
_TOTAL_KEYS = ("total_tokens",)


def _first_of(d: dict, *keys: str, default: int = 0) -> int:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


_agent_counters: dict[str, "TokenCounter"] = {}


class TokenCounter:
    """Accumulate token usage for one agent invocation.

    Usage::

        # In middleware:
        TokenCounter.for_agent(agent_id).add(usage)

        # After agent completes (in persist middleware):
        tc = TokenCounter.get_agent(agent_id)
        token_cost_json = tc.to_json()
        cost = tc.snapshot()["estimated_cost_cny"]
        TokenCounter.remove_agent(agent_id)   # prevent memory leak
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
    def for_agent(cls, agent_id: str, model_name: str = "deepseek-v4-flash") -> "TokenCounter":
        tc = _agent_counters.get(agent_id)
        if tc is None:
            tc = _agent_counters[agent_id] = cls(model_name)
        return tc

    @classmethod
    def get_agent(cls, agent_id: str) -> "TokenCounter | None":
        return _agent_counters.get(agent_id)

    @classmethod
    def remove_agent(cls, agent_id: str) -> None:
        _agent_counters.pop(agent_id, None)

    # -- public API ----------------------------------------------------------

    def add(self, usage: dict | None) -> "TokenCounter":
        if not usage:
            return self

        prompt = _first_of(usage, *_PROMPT_KEYS)
        completion = _first_of(usage, *_COMPLETION_KEYS)
        total = _first_of(usage, *_TOTAL_KEYS, default=prompt + completion)

        input_details = usage.get("input_token_details") or usage.get("prompt_tokens_details") or {}
        output_details = usage.get("output_token_details") or usage.get("completion_tokens_details") or {}

        cache_hit = usage.get("prompt_cache_hit_tokens", 0)
        cache_miss = usage.get("prompt_cache_miss_tokens", 0)
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
        p = _PRICING.get(self.model_name, _PRICING[_FALLBACK_MODEL])
        return (
            self._cache_hit_tokens * p["cache_hit"]
            + self._cache_miss_tokens * p["cache_miss"]
            + self._completion_tokens * p["output"]
        ) / 1_000_000

    def to_json(self) -> dict:
        return {
            "input_tokens": self._prompt_tokens,
            "output_tokens": self._completion_tokens,
            "total_tokens": self._total_tokens,
            "cache_hit_tokens": self._cache_hit_tokens,
            "cache_miss_tokens": self._cache_miss_tokens,
            "reasoning_tokens": self._reasoning_tokens,
        }

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

    def snapshot(self) -> dict:
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
