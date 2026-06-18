"""Summary service — single-turn LLM summarisation with token counting.

Used after file upload / web fetch to populate ``knowledge_files.summary_json``.
Uses ``TokenCounter`` directly (no middleware) since it's a single LLM call.
"""

from __future__ import annotations

from pptgenius.infrastructure.config.settings import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.llm import create_llm
from pptgenius.infrastructure.utils import TokenCounter, get_logger
from langchain_core.messages import SystemMessage, HumanMessage

_log = get_logger("pptgenius.rag.summary")

# ── prompts ─────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "你是一个专业文档摘要助手。用中文输出摘要，控制在 200-500 字以内。"
    "只输出摘要本身，不要包含标题、前缀、或任何格式标记。"
)

_USER_TEMPLATE = """请为以下文档内容生成摘要。

文档文件名: {filename}
文档类型: {file_type}
内容长度: {char_count} 字符

## 内容
{content}
"""

_WEB_USER_TEMPLATE = """请为以下网页内容生成摘要。

网页标题: {title}
网页 URL: {url}
内容长度: {char_count} 字符

## 内容
{content}
"""

# ── content sampler ──────────────────────────────────────────────────

_MAX_INPUT_CHARS = 12_000
_DATA_FILE_TYPES = frozenset({"csv", "xlsx", "xls"})


def _sample_content(text: str) -> str:
    """Take head + tail of long texts so the LLM sees structure and details."""
    if len(text) <= _MAX_INPUT_CHARS:
        return text
    head = text[:_MAX_INPUT_CHARS * 3 // 4]
    tail = text[-_MAX_INPUT_CHARS // 4:]
    return head + f"\n\n... (省略 {len(text) - len(head) - len(tail)} 字符) ...\n\n" + tail


# ── service ──────────────────────────────────────────────────────────

class SummaryService:
    """Generate LLM summaries with token accounting."""

    async def summarize_file(self, db: Database, file_id: int) -> dict:
        """Summarise an uploaded knowledge file.  Writes ``summary_json`` to DB.

        Decision table:
        - docs (pdf/docx/md/txt): LLM summarise
        - data (csv/xlsx) ≤30 lines: skip, summary = null
        - data (csv/xlsx) >30 lines: raw content as summary (free, no LLM)

        Returns ``{summary, token_cost_json, estimated_cost_cny}``.
        """
        kf = await db.get_knowledge_file(file_id)
        if kf is None:
            return {"error": f"knowledge_file {file_id} not found"}

        # Gather full text from chunks
        chunks = await db.list_chunks_by_file(file_id)
        full_text = "\n\n".join(c.chunk_text for c in chunks)

        ft = (kf.file_type or "").lower()

        # ── data file: parser already produces structured output → skip ──
        if ft in _DATA_FILE_TYPES:
            _log.info("data file_id=%d — parser handles summary, skipping LLM", file_id)
            return {
                "summary": None,
                "token_cost_json": _empty_cost(),
                "estimated_cost_cny": 0.0,
            }

        # ── document: LLM summarise ──
        sampled = _sample_content(full_text)

        result = await self._call_llm(
            system_prompt=_SYSTEM_PROMPT,
            user_content=_USER_TEMPLATE.format(
                filename=kf.filename,
                file_type=kf.file_type,
                char_count=len(full_text),
                content=sampled,
            ),
        )

        await db.update_knowledge_file_summary(file_id, result["summary"])
        _log.info("summarised file_id=%d (%d chars → %d chars summary, ¥%.4f)",
                   file_id, len(full_text), len(result["summary"]), result["estimated_cost_cny"])
        return result

    async def summarize_web(self, db: Database, file_id: int,
                            title: str, url: str, text: str,
                            agent_id: str = "") -> dict:
        """Summarise web-scraped content.  Writes ``summary_json`` + ``web_url`` to DB.

        If *agent_id* is provided, accumulates token usage to that agent's
        ``TokenCounter`` (for sub-agent cost tracking).
        """
        sampled = _sample_content(text)

        result = await self._call_llm(
            system_prompt=_SYSTEM_PROMPT,
            user_content=_WEB_USER_TEMPLATE.format(
                title=title, url=url,
                char_count=len(text),
                content=sampled,
            ),
            agent_id=agent_id,
        )

        await db.update_knowledge_file_summary(file_id, result["summary"])
        await db.set_knowledge_file_web_url(file_id, url)
        _log.info("summarised web file_id=%d url=%s (→ %d chars, ¥%.4f)",
                   file_id, url[:60], len(result["summary"]), result["estimated_cost_cny"])
        return result

    # ── internal ──────────────────────────────────────────────────────

    async def _call_llm(self, system_prompt: str, user_content: str,
                        agent_id: str = "") -> dict:
        """Single-turn LLM call with token counting.

        If *agent_id* is provided, accumulates usage to that agent's counter.
        Otherwise uses a local counter and returns billing data only.
        """
        llm, _ = create_llm(conversation_id=0)

        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])

        summary = str(response.content).strip() if response.content else ""

        usage = getattr(response, "usage_metadata", None) or {}

        if agent_id:
            TokenCounter.for_agent(agent_id, model_name=get_settings().llm.model).add(usage)
            # Return minimal cost info — the counter will be read later
            return {
                "summary": summary,
                "token_cost_json": None,
                "estimated_cost_cny": None,
            }

        tc = TokenCounter(model_name=get_settings().llm.model)
        tc.add(usage)
        return {
            "summary": summary,
            "token_cost_json": tc.to_json(),
            "estimated_cost_cny": round(tc.estimate_cost(), 6),
        }


def _empty_cost() -> dict:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_hit_tokens": 0,
        "cache_miss_tokens": 0,
        "reasoning_tokens": 0,
    }


# ── module-level singleton ───────────────────────────────────────────

summary_service = SummaryService()
