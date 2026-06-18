"""Database thin wrapper — holds an AsyncSession, serializes concurrent access."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import (
    conversation as conv_repo,
    cost as cost_repo,
    knowledge as kn_repo,
    message as msg_repo,
    snapshot as snap_repo,
    outline as out_repo,
    ppt as ppt_repo,
    style as style_repo,
    user as user_repo,
)


class Database:
    """Thin wrapper that delegates to repository functions with the session.

    Serializes concurrent access via asyncio.Lock — safe for LangGraph's
    parallel tool execution (ToolNode uses asyncio.gather).
    """

    __slots__ = ("db", "_lock")

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._lock = asyncio.Lock()

    async def _call(self, repo_fn, *a, **kw):
        async with self._lock:
            return await repo_fn(self.db, *a, **kw)

    # ─── user ───
    async def create_user(self, *a, **kw): return await self._call(user_repo.create_user, *a, **kw)
    async def get_user(self, *a, **kw): return await self._call(user_repo.get_user, *a, **kw)
    async def get_user_by_name(self, *a, **kw): return await self._call(user_repo.get_user_by_name, *a, **kw)
    async def get_or_create_default_user(self): return await self._call(user_repo.get_or_create_default_user)
    async def delete_user(self, *a, **kw): return await self._call(user_repo.delete_user, *a, **kw)
    async def update_user_other(self, *a, **kw): return await self._call(user_repo.update_user_other, *a, **kw)
    async def get_rag_mode(self, *a, **kw): return await self._call(user_repo.get_rag_mode, *a, **kw)
    async def set_rag_mode(self, *a, **kw): return await self._call(user_repo.set_rag_mode, *a, **kw)
    async def get_web_search_enabled(self, *a, **kw): return await self._call(user_repo.get_web_search_enabled, *a, **kw)
    async def set_web_search_enabled(self, *a, **kw): return await self._call(user_repo.set_web_search_enabled, *a, **kw)
    async def set_rag_index_changed(self, *a, **kw): return await self._call(user_repo.set_rag_index_changed, *a, **kw)
    async def clear_rag_index_changed(self, *a, **kw): return await self._call(user_repo.clear_rag_index_changed, *a, **kw)
    async def is_rag_index_changed(self, *a, **kw): return await self._call(user_repo.is_rag_index_changed, *a, **kw)

    # ─── conversation ───
    async def create_conversation(self, *a, **kw): return await self._call(conv_repo.create_conversation, *a, **kw)
    async def get_conversation(self, *a, **kw): return await self._call(conv_repo.get_conversation, *a, **kw)
    async def list_conversations(self, *a, **kw): return await self._call(conv_repo.list_conversations, *a, **kw)
    async def update_conversation_title(self, *a, **kw): return await self._call(conv_repo.update_conversation_title, *a, **kw)
    async def update_conversation_phase(self, *a, **kw): return await self._call(conv_repo.update_conversation_phase, *a, **kw)
    async def set_conversation_outline(self, *a, **kw): return await self._call(conv_repo.set_conversation_outline, *a, **kw)
    async def archive_conversation(self, *a, **kw): return await self._call(conv_repo.archive_conversation, *a, **kw)
    async def soft_delete_conversation(self, *a, **kw): return await self._call(conv_repo.soft_delete_conversation, *a, **kw)

    # ─── message ───
    async def create_message(self, *a, **kw): return await self._call(msg_repo.create_message, *a, **kw)
    async def create_human_message(self, *a, **kw): return await self._call(msg_repo.create_human_message, *a, **kw)
    async def create_document_message(self, *a, **kw): return await self._call(msg_repo.create_document_message, *a, **kw)
    async def get_messages_by_conversation(self, *a, **kw): return await self._call(msg_repo.get_messages_by_conversation, *a, **kw)
    async def count_messages_by_conversation(self, *a, **kw): return await self._call(msg_repo.count_messages_by_conversation, *a, **kw)
    async def trim_messages(self, *a, **kw): return await self._call(msg_repo.trim_messages, *a, **kw)
    async def update_message_token_cost(self, *a, **kw): return await self._call(msg_repo.update_message_token_cost, *a, **kw)
    async def set_message_cost(self, *a, **kw): return await self._call(msg_repo.set_message_cost, *a, **kw)

    # ─── outline ───
    async def create_outline(self, *a, **kw): return await self._call(out_repo.create_outline, *a, **kw)
    async def set_outline_title(self, *a, **kw): return await self._call(out_repo.set_outline_title, *a, **kw)
    async def get_outline(self, *a, **kw): return await self._call(out_repo.get_outline, *a, **kw)
    async def list_outlines_by_conversation(self, *a, **kw): return await self._call(out_repo.list_outlines_by_conversation, *a, **kw)
    async def list_outlines_by_user(self, *a, **kw): return await self._call(out_repo.list_outlines_by_user, *a, **kw)
    async def update_outline_status(self, *a, **kw): return await self._call(out_repo.update_outline_status, *a, **kw)
    async def update_outline_eval(self, *a, **kw): return await self._call(out_repo.update_outline_eval, *a, **kw)
    async def increase_outline_version(self, *a, **kw): return await self._call(out_repo.increase_outline_version, *a, **kw)
    async def set_outline_explore_result(self, *a, **kw): return await self._call(out_repo.set_outline_explore_result, *a, **kw)
    async def get_outline_explore_result(self, *a, **kw): return await self._call(out_repo.get_outline_explore_result, *a, **kw)
    async def soft_delete_outline(self, *a, **kw): return await self._call(out_repo.soft_delete_outline, *a, **kw)
    # outline_slide
    async def create_outline_slide(self, *a, **kw): return await self._call(out_repo.create_outline_slide, *a, **kw)
    async def get_outline_slide(self, *a, **kw): return await self._call(out_repo.get_outline_slide, *a, **kw)
    async def get_slides_by_outline_id(self, *a, **kw): return await self._call(out_repo.get_slides_by_outline_id, *a, **kw)
    async def update_outline_slide(self, *a, **kw): return await self._call(out_repo.update_outline_slide, *a, **kw)
    async def update_outline_slide_index(self, *a, **kw): return await self._call(out_repo.update_outline_slide_index, *a, **kw)
    async def update_outline_slide_citations(self, *a, **kw): return await self._call(out_repo.update_outline_slide_citations, *a, **kw)
    async def update_outline_slide_status(self, *a, **kw): return await self._call(out_repo.update_outline_slide_status, *a, **kw)
    async def soft_delete_outline_slide(self, *a, **kw): return await self._call(out_repo.soft_delete_outline_slide, *a, **kw)
    async def delete_outline_slide(self, *a, **kw): return await self._call(out_repo.delete_outline_slide, *a, **kw)
    async def insert_outline_slide_after(self, *a, **kw): return await self._call(out_repo.insert_outline_slide_after, *a, **kw)
    async def replace_outline_slides(self, *a, **kw): return await self._call(out_repo.replace_outline_slides, *a, **kw)
    async def replace_section_slides(self, *a, **kw): return await self._call(out_repo.replace_section_slides, *a, **kw)
    # outline_section
    async def create_outline_section(self, *a, **kw): return await self._call(out_repo.create_outline_section, *a, **kw)
    async def get_outline_section(self, *a, **kw): return await self._call(out_repo.get_outline_section, *a, **kw)
    async def get_sections_by_outline_id(self, *a, **kw): return await self._call(out_repo.get_sections_by_outline_id, *a, **kw)
    async def update_outline_section(self, *a, **kw): return await self._call(out_repo.update_outline_section, *a, **kw)
    async def delete_outline_section(self, *a, **kw): return await self._call(out_repo.delete_outline_section, *a, **kw)

    # ─── ppt ───
    async def create_presentation(self, *a, **kw): return await self._call(ppt_repo.create_presentation, *a, **kw)
    async def get_presentation(self, *a, **kw): return await self._call(ppt_repo.get_presentation, *a, **kw)
    async def list_presentations_by_conversation(self, *a, **kw): return await self._call(ppt_repo.list_presentations_by_conversation, *a, **kw)
    async def list_presentations_by_user(self, *a, **kw): return await self._call(ppt_repo.list_presentations_by_user, *a, **kw)
    async def update_presentation_status(self, *a, **kw): return await self._call(ppt_repo.update_presentation_status, *a, **kw)
    async def set_presentation_style(self, *a, **kw): return await self._call(ppt_repo.set_presentation_style, *a, **kw)
    async def increment_presentation_version(self, *a, **kw): return await self._call(ppt_repo.increment_presentation_version, *a, **kw)
    async def soft_delete_presentation(self, *a, **kw): return await self._call(ppt_repo.soft_delete_presentation, *a, **kw)
    # presentation_slide
    async def create_presentation_slide(self, *a, **kw): return await self._call(ppt_repo.create_presentation_slide, *a, **kw)
    async def create_presentation_slides_batch(self, *a, **kw): return await self._call(ppt_repo.create_presentation_slides_batch, *a, **kw)
    async def get_presentation_slide(self, *a, **kw): return await self._call(ppt_repo.get_presentation_slide, *a, **kw)
    async def get_slides_by_presentation_id(self, *a, **kw): return await self._call(ppt_repo.get_slides_by_presentation_id, *a, **kw)
    async def set_slide_agent_output(self, *a, **kw): return await self._call(ppt_repo.set_slide_agent_output, *a, **kw)
    async def update_slide_status(self, *a, **kw): return await self._call(ppt_repo.update_slide_status, *a, **kw)
    async def update_slides_style(self, *a, **kw): return await self._call(ppt_repo.update_slides_style, *a, **kw)
    async def soft_delete_presentation_slide(self, *a, **kw): return await self._call(ppt_repo.soft_delete_presentation_slide, *a, **kw)
    async def delete_presentation_slide(self, *a, **kw): return await self._call(ppt_repo.delete_presentation_slide, *a, **kw)
    async def replace_presentation_slides(self, *a, **kw): return await self._call(ppt_repo.replace_presentation_slides, *a, **kw)

    # ─── style ───
    async def create_style(self, *a, **kw): return await self._call(style_repo.create_style, *a, **kw)
    async def get_style(self, *a, **kw): return await self._call(style_repo.get_style, *a, **kw)
    async def search_styles(self, *a, **kw): return await self._call(style_repo.search_styles, *a, **kw)

    # ─── knowledge ───
    async def create_knowledge_file(self, *a, **kw): return await self._call(kn_repo.create_knowledge_file, *a, **kw)
    async def get_knowledge_file(self, *a, **kw): return await self._call(kn_repo.get_knowledge_file, *a, **kw)
    async def list_knowledge_files(self, *a, **kw): return await self._call(kn_repo.list_knowledge_files, *a, **kw)
    async def update_knowledge_file_status(self, *a, **kw): return await self._call(kn_repo.update_knowledge_file_status, *a, **kw)
    async def update_knowledge_file_summary(self, *a, **kw): return await self._call(kn_repo.update_knowledge_file_summary, *a, **kw)
    async def set_knowledge_file_web_url(self, *a, **kw): return await self._call(kn_repo.set_knowledge_file_web_url, *a, **kw)
    async def delete_knowledge_file(self, *a, **kw): return await self._call(kn_repo.delete_knowledge_file, *a, **kw)
    # chunks
    async def create_chunk(self, *a, **kw): return await self._call(kn_repo.create_chunk, *a, **kw)
    async def get_chunk_by_id(self, *a, **kw): return await self._call(kn_repo.get_chunk_by_id, *a, **kw)
    async def list_chunks_by_file(self, *a, **kw): return await self._call(kn_repo.list_chunks_by_file, *a, **kw)
    async def get_all_chunks_for_user(self, *a, **kw): return await self._call(kn_repo.get_all_chunks_for_user, *a, **kw)
    async def get_all_chunks_for_conversation(self, *a, **kw): return await self._call(kn_repo.get_all_chunks_for_conversation, *a, **kw)
    async def get_chunks_for_user_filter_web(self, *a, **kw): return await self._call(kn_repo.get_chunks_for_user_filter_web, *a, **kw)
    async def get_chunks_for_conversation_filter_web(self, *a, **kw): return await self._call(kn_repo.get_chunks_for_conversation_filter_web, *a, **kw)

    # ─── snapshot ───
    async def create_snapshot(self, *a, **kw): return await self._call(snap_repo.create_snapshot, *a, **kw)
    async def get_snapshot(self, *a, **kw): return await self._call(snap_repo.get_snapshot, *a, **kw)
    async def list_snapshots_by_presentation(self, *a, **kw): return await self._call(snap_repo.list_snapshots_by_presentation, *a, **kw)
    async def get_latest_snapshot(self, *a, **kw): return await self._call(snap_repo.get_latest_snapshot, *a, **kw)
    async def delete_snapshot(self, *a, **kw): return await self._call(snap_repo.delete_snapshot, *a, **kw)
    # outline_snapshot
    async def create_outline_snapshot(self, *a, **kw): return await self._call(snap_repo.create_outline_snapshot, *a, **kw)
    async def get_outline_snapshot(self, *a, **kw): return await self._call(snap_repo.get_outline_snapshot, *a, **kw)
    async def list_outline_snapshots(self, *a, **kw): return await self._call(snap_repo.list_outline_snapshots, *a, **kw)
    async def get_latest_outline_snapshot(self, *a, **kw): return await self._call(snap_repo.get_latest_outline_snapshot, *a, **kw)
    async def delete_outline_snapshot(self, *a, **kw): return await self._call(snap_repo.delete_outline_snapshot, *a, **kw)

    # ─── cost ───
    async def cost_summary(self, *a, **kw): return await self._call(cost_repo.cost_summary, *a, **kw)
    async def cost_by_date(self, *a, **kw): return await self._call(cost_repo.cost_by_date, *a, **kw)
    async def cost_by_conversation(self, *a, **kw): return await self._call(cost_repo.cost_by_conversation, *a, **kw)
