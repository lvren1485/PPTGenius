"""Knowledge Agent — reads files, takes notes, suggests outline structure."""

from __future__ import annotations

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
from .knowledge_tools import make_read_file

_log = get_logger("pptgenius.agent.outline.knowledge")


def _get_writer():
    try:
        return get_stream_writer()
    except (RuntimeError, KeyError):
        return lambda _: None


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return (RESOURCES_DIR / "prompts" / "outline" / "knowledge_system.md").read_text(encoding="utf-8")


# ── notebook tool (append-only, callable multiple times) ────────────────────


def _make_submit_note():
    notes: list[str] = []

    @tool
    async def submit_note(text: str) -> str:
        """Append a note to the exploration notebook. Can be called multiple times.

        Use this to record key findings, file summaries, topic ideas as you read.
        Args:
            text: The note content to append.
        """
        notes.append(text)
        return f"已记录 ({len(notes)}条)"

    return submit_note, notes


# ── main entry ───────────────────────────────────────────────────────────────


async def run_knowledge_agent(
    db: Database,
    conversation_id: int,
    *,
    query: str | None = None,
    file_ids: list[int] | None = None,
) -> dict:
    """Explore knowledge files and suggest outline structure."""
    writer = _get_writer()

    conv = await db.get_conversation(conversation_id)
    if conv is None:
        return {"error": "对话不存在"}
    user_id = conv.user_id

    kf_list = await db.list_knowledge_files(user_id, conversation_id=conversation_id)
    if file_ids:
        kf_list = [f for f in kf_list if f.id in file_ids]

    user_prompt_parts = ["请探索以下知识文件："]
    if not kf_list:
        return {"result": "当前没有上传文件。", "status": "ok"}
    for kf in kf_list:
        user_prompt_parts.append(f"  - [{kf.id}] {kf.filename} ({kf.file_type})")
    if query:
        user_prompt_parts.append(f"\n用户需求: {query}")
    user_prompt_parts.append("\n使用 read_file 逐个阅读文件，用 submit_note 记录要点。读完所有文件后，在最后一条消息中给出PPT大纲结构建议。")
    user_prompt = "\n".join(user_prompt_parts)

    read_count = [0]
    fetched_ids: set[int] = set()
    submit_note, notes = _make_submit_note()

    tools = [make_read_file(db, read_count, fetched_ids), submit_note]

    llm, agent_id, mw = build_llm(conversation_id)
    push_agent(conversation_id, agent_id)
    agent = create_agent(
        model=llm, tools=tools,
        system_prompt=_load_system_prompt(),
        middleware=[mw],
    )

    writer({"type": "knowledge_agent_start"})

    # ── first attempt ──
    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            config={"recursion_limit": 50},
        )
    except Exception:
        _log.warning("knowledge agent failed conv=%d — retrying", conversation_id)
        result = {"messages": [HumanMessage(content=user_prompt)]}

    writer({"type": "knowledge_agent_end"})

    # ── extract result ──
    final_text = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            final_text = str(msg.content)
            break

    # ── retry if no useful output ──
    if not final_text and not notes:
        _log.warning("knowledge agent no output conv=%d — retrying", conversation_id)
        chain = list(result["messages"])
        for i in range(len(chain) - 1, -1, -1):
            if isinstance(chain[i], AIMessage):
                if not chain[i].content or not str(chain[i].content).strip():
                    chain[i] = AIMessage(
                        content="（已读取文件，但未输出结构建议）",
                        tool_calls=chain[i].tool_calls,
                    )
                break
        retry_prompt = user_prompt + "\n\n**重要：读完所有文件后必须直接在最后一条消息中输出大纲结构建议，不要再调用工具。**"
        try:
            result2 = await agent.ainvoke(
                {"messages": chain + [HumanMessage(content=retry_prompt)]},
                config={"recursion_limit": 30},
            )
            final_text = ""
            for msg in reversed(result2["messages"]):
                if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                    final_text = str(msg.content)
                    break
        except Exception:
            _log.warning("knowledge agent retry failed conv=%d", conversation_id)

    if not final_text and not notes:
        return {"error": "知识探索未产生有效结果", "status": "error"}

    # If no final text but notes collected — call LLM once without tools
    if not final_text and notes:
        _log.info("no final output — calling LLM with notes")
        try:
            llm2, _, _ = build_llm(conversation_id)
            notes_text = "\n\n---\n\n".join(notes)
            summary_prompt = f"""基于以下文件探索笔记，给出PPT大纲结构建议。

## 笔记
{notes_text}

## 用户需求
{query or '根据笔记内容生成PPT大纲'}

请给出：1. 大纲标题 2. 章节划分（每节含描述和页数） 3. 总共12页"""
            response = await llm2.ainvoke([HumanMessage(content=summary_prompt)])
            final_text = str(response.content)
        except Exception:
            _log.warning("knowledge agent fallback LLM call failed")

    # Compress notes + structure into one result
    parts = []
    if notes:
        parts.append("## 文件要点\n" + "\n".join(f"- {n[:300]}" for n in notes))
    if final_text:
        parts.append("## 结构建议\n" + final_text[:3000])
    result_text = "\n\n".join(parts) if parts else "(无结果)"

    return {"result": result_text, "status": "ok"}
