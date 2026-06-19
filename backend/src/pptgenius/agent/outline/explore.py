"""Explore Agent — reads file summaries, searches RAG + web, suggests outline structure.

Replaces the old knowledge agent.  Key differences:
- No ``read_file`` tool — summaries are injected directly into the prompt.
- Higher tool limits (12/8/6 instead of 5/6/4).
- No ``_WRITE_HINT`` — explore outputs structured JSON, not slides.
"""

from __future__ import annotations

from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.config.settings import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.middleware import build_middlewares
from pptgenius.infrastructure.llm import create_llm
from .knowledge_tools import (
    make_search_knowledge,
    make_search_web,
    make_fetch_web,
    _EXPLORE_KB_LIMIT,
    _EXPLORE_WEB_LIMIT,
    _EXPLORE_FETCH_LIMIT,
)

_log = get_logger("pptgenius.agent.outline.explore")


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


def _build_file_summaries(kf_list) -> str:
    """Format file summaries for the prompt.  Skips files without summary."""
    lines = []
    count = 0
    for kf in kf_list:
        summary = kf.summary_json or ""
        if not summary.strip():
            lines.append(f"- [{kf.id}] **{kf.filename}** ({kf.file_type}) — 无摘要")
        else:
            lines.append(f"- [{kf.id}] **{kf.filename}** ({kf.file_type})\n  {summary}")
        count += 1
    header = f"共 {count} 个文件："
    return header + "\n" + "\n".join(lines) if lines else "无文件。"


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    path = RESOURCES_DIR / "prompts" / "outline" / "explore_system.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "你是 PPT 大纲探索专家。基于文件摘要和搜索结果，规划 PPT 大纲结构。"


async def run_explore_agent(
    db: Database,
    conversation_id: int,
    *,
    query: str | None = None,
    file_ids: list[int] | None = None,
) -> dict:
    """Explore knowledge files (via summaries) + web → outline structure."""
    writer = _get_writer()

    conv = await db.get_conversation(conversation_id)
    if conv is None:
        return {"error": "对话不存在"}
    user_id = conv.user_id

    rag_mode = await db.get_rag_mode(user_id)
    web_enabled = await db.get_web_search_enabled(user_id)

    # Build BM25 index for this explore session
    from pptgenius.infrastructure.rag.knowledge import knowledge_service
    _index_scope = ""
    _index_scope = await knowledge_service.build_index(
        db, user_id=user_id, rag_mode=rag_mode,
        filter_web=not web_enabled, conversation_id=conversation_id,
    )

    # ── Read old explore result if modifying an existing outline ──
    old_explore = ""
    if conv.current_outline_id:
        outline = await db.get_outline(conv.current_outline_id)
        if outline and outline.explore_result_json:
            old_explore = str(outline.explore_result_json)[:8_000]

    # ── Build file summary section ──
    kf_list = await db.list_knowledge_files(user_id, conversation_id=conversation_id)
    if file_ids:
        kf_list = [f for f in kf_list if f.id in file_ids]
    summary_section = _build_file_summaries(kf_list)

    # ── User prompt ──
    user_prompt = f"""## 用户需求
{query or '根据文件内容生成PPT大纲'}

## 文件摘要
{summary_section}"""

    if old_explore:
        user_prompt += f"""

## 上次探索结果（供参考）
{old_explore}

请基于上次结果和新的需求，更新或补充大纲结构。只修改需要变化的部分。"""

    user_prompt += "\n\n请先理解所有文件摘要，然后用工具搜索补充信息，最后输出 JSON 格式的大纲结构建议。"
    if not web_enabled:
        user_prompt += (
            "\n\n**重要：网络搜索功能已关闭。**"
            "你只能使用 search_knowledge 搜索知识库内的已有文件。"
            "每个 section 选择最相关的 2-5 个 file_id 和 chunk_id 填入输出。"
        )

    # ── Build LLM first (agent_id needed for fetch_web token tracking) ──
    llm, agent_id = create_llm(conversation_id)

    # ── Tools ──
    kb_count = [0]
    web_count = [0]
    fetch_count = [0]

    tools = [
        make_search_knowledge(
            db, user_id, conversation_id, rag_mode, kb_count,
            filter_web=not web_enabled, limit=_EXPLORE_KB_LIMIT,
        ),
    ]
    if web_enabled:
        tools.append(make_search_web(web_count, limit=_EXPLORE_WEB_LIMIT))
        tools.append(make_fetch_web(db, user_id, conversation_id, fetch_count,
                                    agent_id=agent_id, limit=_EXPLORE_FETCH_LIMIT))
    mws, _ = build_middlewares(conversation_id, agent_id)
    push_agent(conversation_id, agent_id)

    agent = create_agent(
        model=llm, tools=tools,
        system_prompt=_load_system_prompt(),
        middleware=mws,
    )

    writer({"type": "explore_agent_start"})

    try:
        try:
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=user_prompt)]},
                config={"recursion_limit": 80},
            )
        except Exception:
            _log.warning("explore agent failed conv=%d", conversation_id)
            _log.debug("explore crash detail", exc_info=True)
            return {"error": "探索失败，请重试"}

        # ── Extract final output ──
        final_text = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                final_text = str(msg.content)
                break

        if not final_text:
            _log.warning("explore agent no final output conv=%d", conversation_id)
            return {"error": "探索未产生有效结果"}

        return {"result": final_text, "status": "ok"}
    finally:
        knowledge_service.remove_index(_index_scope)
