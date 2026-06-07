"""Summarize file tool — thin wrapper for knowledge file summarization."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.tool_sse_wrapper import wrap_tool_with_sse

_log = get_logger("pptgenius.agent.tools.summarize_file")


def make_summarize_file(db: Database, conversation_id: int) -> Callable:

    async def _summarize_file(file_id: int) -> str:
        """Generate an LLM summary for a knowledge file.

        Call when get_knowledge_files shows has_full_summary=false for a file.
        Summary is cached in knowledge_files.summary_json.

        Args:
            file_id: The id of the knowledge file to summarize.
        """
        kf = await db.get_knowledge_file(file_id)
        if kf is None:
            return f"错误: 知识文件 {file_id} 不存在"

        if kf.summary_json is not None:
            return f"文件'{kf.filename}'已有摘要，无需重复生成"

        # TODO Phase 4: wire real summarization via SummaryAgent
        _log.info("summarize_file stub: file='%s' type=%s", kf.filename, kf.file_type)
        return f"文件'{kf.filename}'摘要生成待实现"

    return tool(wrap_tool_with_sse(_summarize_file))
