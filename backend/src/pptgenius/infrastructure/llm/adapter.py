"""DeepSeek V4 适配层 — 修复 LangChain 与 DeepSeek Thinking Mode 兼容性。

问题：
  DeepSeek V4 默认开启 thinking mode，每轮 assistant 响应携带 `reasoning_content`。
  多轮 Tool Calling 时，必须将上一轮的 `reasoning_content` 原样传回，否则 API 返回 400。

根因：
  LangChain 的 ChatOpenAI 在两个地方丢失了 `reasoning_content`：
  1. `_create_chat_result` — 从 OpenAI SDK 响应构建 AIMessage 时未提取该字段
  2. `_convert_message_to_dict` — 将 AIMessage 序列化为 API 请求时未注入该字段

用法：
  from pptgenius.infrastructure.llm import apply_deepseek_patch

  apply_deepseek_patch()  # 在创建任何 ChatOpenAI 实例之前调用一次即可
"""

from __future__ import annotations

import langchain_openai.chat_models.base as _base
from langchain_core.messages import AIMessage, BaseMessage


_patched = False

# ── Patch 1: 提取 reasoning_content ──

_original_create_chat_result = _base.BaseChatOpenAI._create_chat_result


def _patched_create_chat_result(self, response, generation_info=None):
    result = _original_create_chat_result(self, response, generation_info)

    msg = response.choices[0].message
    reasoning = _extract_reasoning(msg)

    if reasoning and result.generations:
        for gen in result.generations:
            gen.message.additional_kwargs["reasoning_content"] = reasoning

    return result


# ── Patch 2: 注入 reasoning_content (含递归处理 tool calling 链) ──

_original_convert_message_to_dict = _base._convert_message_to_dict


def _patched_convert_message_to_dict(
    message: BaseMessage, api: str = "chat/completions"
) -> dict:
    message_dict = _original_convert_message_to_dict(message, api)

    if isinstance(message, AIMessage):
        rc = message.additional_kwargs.get("reasoning_content")
        if rc:
            message_dict["reasoning_content"] = rc

    return message_dict


# ── Diagnostic: log message structure on 400 ──

def _install_diagnostic_hook():
    """Wrap _agenerate to log message structure when 400 occurs."""
    from pptgenius.infrastructure.utils import get_logger
    _diag_log = get_logger("pptgenius.llm.diag")

    _original_agenerate = _base.BaseChatOpenAI._agenerate

    async def _diag_agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            return await _original_agenerate(self, messages, stop, run_manager, **kwargs)
        except Exception as e:
            if "400" in str(e) or "insufficient tool messages" in str(e):
                roles = []
                for m in messages:
                    tc_count = len(m.tool_calls) if hasattr(m, "tool_calls") and m.tool_calls else 0
                    tc_ids = [tc.get("id", "")[:8] for tc in (m.tool_calls or [])] if tc_count else []
                    roles.append(f"{m.__class__.__name__}(tc={tc_count}{' ids='+','.join(tc_ids) if tc_ids else ''})")
                _diag_log.warning(
                    "400 diag: %d messages: %s",
                    len(messages), " → ".join(roles[-8:])  # last 8
                )
            raise

    _base.BaseChatOpenAI._agenerate = _diag_agenerate


def _extract_reasoning(msg) -> str | None:
    """从 OpenAI SDK ChatCompletionMessage 中提取 reasoning_content。"""
    rc = getattr(msg, "reasoning_content", None)
    if rc:
        return rc
    extra = getattr(msg, "model_extra", None)
    if extra:
        return extra.get("reasoning_content", None)
    return None


def apply_deepseek_patch() -> bool:
    """安装 DeepSeek V4 适配补丁。幂等，重复调用无副作用。"""
    global _patched

    if _patched:
        return False

    _base.BaseChatOpenAI._create_chat_result = _patched_create_chat_result
    _base._convert_message_to_dict = _patched_convert_message_to_dict
    _install_diagnostic_hook()
    _patched = True
    return True


def is_patched() -> bool:
    """检查补丁是否已安装。"""
    return _patched
