"""Knowledge Agent — explores files and suggests outline structure."""

from __future__ import annotations

import json
from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from pptgenius.infrastructure.config.settings import RESOURCES_DIR
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.agent_registry import push_agent
from ..common.model_builder import build_llm
from .knowledge_tools import (
    make_fetch_web,
    make_read_file,
    make_search_knowledge,
    make_search_web,
)

_log = get_logger("pptgenius.agent.outline.knowledge")


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return (RESOURCES_DIR / "prompts" / "outline" / "knowledge_system.md").read_text(encoding="utf-8")


# ── submit tool ──────────────────────────────────────────────────────────────


def _make_submit_exploration():
    _called: list[bool] = [False]

    @tool
    async def submit_exploration(
        files_summary: list[dict],
        suggested_structure: dict,
    ) -> str:
        """Submit the knowledge exploration result. MUST be called last.

        Parameters
        ----------
        files_summary : list[dict] — [{file_id, filename, overview, suggested_usage}, ...]
        suggested_structure : dict — {title, sections: [{section_index, title, description, slide_number, source_files}]}
        """
        _called[0] = True
        return json.dumps({
            "files_summary": files_summary,
            "suggested_structure": suggested_structure,
            "status": "ok",
        }, ensure_ascii=False)

    return submit_exploration, _called


# ── main entry ───────────────────────────────────────────────────────────────


async def run_knowledge_agent(
    db: Database,
    conversation_id: int,
    *,
    query: str | None = None,
    file_ids: list[int] | None = None,
) -> dict:
    """Explore knowledge files and suggest outline structure.

    Returns ``{files_summary: [...], suggested_structure: {...}}``.
    """
    writer = _get_writer()

    conv = await db.get_conversation(conversation_id)
    if conv is None:
        return {"error": "对话不存在"}
    user_id = conv.user_id
    rag_mode = await db.get_rag_mode(user_id) if user_id else "user"

    kb_count = [0]
    web_count = [0]
    fetch_count = [0]
    read_count = [0]
    fetched_ids: set[int] = set()

    submit_tool, was_called = _make_submit_exploration()
    tools = [
        make_search_knowledge(db, user_id, conversation_id, rag_mode, kb_count),
        make_search_web(web_count),
        make_fetch_web(db, user_id, conversation_id, fetch_count),
        make_read_file(db, read_count, fetched_ids),
        submit_tool,
    ]

    system_prompt = _load_system_prompt()

    user_prompt_parts = ["请探索以下知识文件并给出大纲结构建议。"]
    if file_ids:
        user_prompt_parts.append(f"\n指定文件 ID: {file_ids}")
        kf_list = await db.list_knowledge_files(user_id, conversation_id=conversation_id)
        for fid in file_ids:
            kf = next((f for f in kf_list if f.id == fid), None)
            if kf:
                user_prompt_parts.append(f"  - [{fid}] {kf.filename} ({kf.file_type})")
    else:
        kf_list = await db.list_knowledge_files(user_id, conversation_id=conversation_id)
        if kf_list:
            user_prompt_parts.append("\n可用文件:")
            for kf in kf_list:
                user_prompt_parts.append(f"  - [{kf.id}] {kf.filename} ({kf.file_type})")
        else:
            user_prompt_parts.append("\n当前没有上传文件。")
    if query:
        user_prompt_parts.append(f"\n用户需求: {query}")
    user_prompt_parts.append("\n请先阅读文件，然后使用 submit_exploration 提交结果。")

    user_prompt = "\n".join(user_prompt_parts)

    llm, agent_id, mw = build_llm(conversation_id)
    push_agent(conversation_id, agent_id)
    agent = create_agent(
        model=llm, tools=tools,
        system_prompt=system_prompt,
        middleware=[mw],
    )

    writer({"type": "knowledge_agent_start"})
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config={"recursion_limit": 20},
    )

    if not was_called[0]:
        _log.warning("submit_exploration not called — retrying")
        retry_msg = HumanMessage(content="请立即调用 submit_exploration 提交探索结果。不要再搜索或分析。")
        clean = list(result["messages"])
        while clean and isinstance(clean[-1], AIMessage) and clean[-1].tool_calls:
            clean.pop()
        await agent.ainvoke(
            {"messages": clean + [retry_msg]},
            config={"recursion_limit": 10},
        )

    writer({"type": "knowledge_agent_end"})

    # Extract result from submit_exploration ToolMessage
    for msg in reversed(result["messages"]):
        name = getattr(msg, "name", "")
        if name == "submit_exploration":
            try:
                return json.loads(str(msg.content))
            except (json.JSONDecodeError, TypeError):
                return {"error": "解析探索结果失败"}
    return {"error": "submit_exploration 未被调用"}
