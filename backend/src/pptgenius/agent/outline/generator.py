"""Outline content generator sub-agent — ReAct agent for generating slide content."""

from __future__ import annotations

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

from ..common.model_builder import build_llm
from ..common.token_middleware import persist_agent_tokens
from .prompts import build_generator_system_prompt, build_generator_user_prompt

_log = get_logger("pptgenius.agent.outline.generator")


async def run_outline_generator(
    db: Database,
    conversation_id: int,
    section_id: int,
    *,
    query: str | None = None,
    knowledge_mode: str = "auto",
    regenerate_slides: list[int] | None = None,
) -> str:
    """Run the outline content generator for one section.

    Returns a confirmation message.  Token cost is persisted to the tool's
    message row via persist_agent_tokens.

    Phase 3: stub — Phase 4 will wire the full ReAct agent with search tools.
    """
    section = await db.get_outline_section(section_id)
    if section is None:
        return f"错误: section {section_id} 不存在"

    title = section.title or "未命名章节"
    desc = section.description or ""
    slides = await db.get_slides_by_outline_id(section.outline_id)
    slide_titles = [s.title for s in slides if s.section_id == section_id]

    _log.info(
        "outline generator stub: section='%s' mode=%s slides=%d",
        title, knowledge_mode, len(slide_titles),
    )

    is_regen = bool(regenerate_slides)
    _system = build_generator_system_prompt()
    _user = build_generator_user_prompt(title, desc, query, slide_titles, is_regen)

    # TODO Phase 4: create full ReAct agent with search_knowledge, search_web,
    # fetch_web, read_file, write_outline_slides tools.
    # llm, agent_id, mw = build_llm(conversation_id)
    # agent = create_agent(llm, tools, system_prompt=_system, middleware=[mw])
    # result = await agent.ainvoke({"messages": [HumanMessage(content=_user)]})
    # await persist_agent_tokens(db, message_id, agent_id)

    return f"章节'{title}'内容生成待实现 (knowledge_mode={knowledge_mode}, slides={len(slide_titles)})"
