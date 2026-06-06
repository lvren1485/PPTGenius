"""Database 薄包装 — 持有 AsyncSession，自动传入 db 参数给各 repository 函数."""

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
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── user ───
    async def create_user(self, *a, **kw): return await user_repo.create_user(self.db, *a, **kw)
    async def get_user(self, *a, **kw): return await user_repo.get_user(self.db, *a, **kw)
    async def get_user_by_name(self, *a, **kw): return await user_repo.get_user_by_name(self.db, *a, **kw)
    async def get_or_create_default_user(self): return await user_repo.get_or_create_default_user(self.db)
    async def delete_user(self, *a, **kw): return await user_repo.delete_user(self.db, *a, **kw)

    # ─── conversation ───
    async def create_conversation(self, *a, **kw): return await conv_repo.create_conversation(self.db, *a, **kw)
    async def get_conversation(self, *a, **kw): return await conv_repo.get_conversation(self.db, *a, **kw)
    async def list_conversations(self, *a, **kw): return await conv_repo.list_conversations(self.db, *a, **kw)
    async def update_conversation_title(self, *a, **kw): return await conv_repo.update_conversation_title(self.db, *a, **kw)
    async def update_conversation_phase(self, *a, **kw): return await conv_repo.update_conversation_phase(self.db, *a, **kw)
    async def set_conversation_outline(self, *a, **kw): return await conv_repo.set_conversation_outline(self.db, *a, **kw)
    async def archive_conversation(self, *a, **kw): return await conv_repo.archive_conversation(self.db, *a, **kw)
    async def soft_delete_conversation(self, *a, **kw): return await conv_repo.soft_delete_conversation(self.db, *a, **kw)

    # ─── message ───
    async def create_message(self, *a, **kw): return await msg_repo.create_message(self.db, *a, **kw)
    async def create_human_message(self, *a, **kw): return await msg_repo.create_human_message(self.db, *a, **kw)
    async def create_document_message(self, *a, **kw): return await msg_repo.create_document_message(self.db, *a, **kw)
    async def get_messages_by_conversation(self, *a, **kw): return await msg_repo.get_messages_by_conversation(self.db, *a, **kw)
    async def count_messages_by_conversation(self, *a, **kw): return await msg_repo.count_messages_by_conversation(self.db, *a, **kw)
    async def trim_messages(self, *a, **kw): return await msg_repo.trim_messages(self.db, *a, **kw)
    async def update_message_token_cost(self, *a, **kw): return await msg_repo.update_message_token_cost(self.db, *a, **kw)

    # ─── outline ───
    async def create_outline(self, *a, **kw): return await out_repo.create_outline(self.db, *a, **kw)
    async def get_outline(self, *a, **kw): return await out_repo.get_outline(self.db, *a, **kw)
    async def list_outlines_by_conversation(self, *a, **kw): return await out_repo.list_outlines_by_conversation(self.db, *a, **kw)
    async def list_outlines_by_user(self, *a, **kw): return await out_repo.list_outlines_by_user(self.db, *a, **kw)
    async def update_outline_status(self, *a, **kw): return await out_repo.update_outline_status(self.db, *a, **kw)
    async def update_outline_eval(self, *a, **kw): return await out_repo.update_outline_eval(self.db, *a, **kw)
    async def increase_outline_version(self, *a, **kw): return await out_repo.increase_outline_version(self.db, *a, **kw)
    async def soft_delete_outline(self, *a, **kw): return await out_repo.soft_delete_outline(self.db, *a, **kw)
    # outline_slide
    async def create_outline_slide(self, *a, **kw): return await out_repo.create_outline_slide(self.db, *a, **kw)
    async def get_outline_slide(self, *a, **kw): return await out_repo.get_outline_slide(self.db, *a, **kw)
    async def get_slides_by_outline_id(self, *a, **kw): return await out_repo.get_slides_by_outline_id(self.db, *a, **kw)
    async def update_outline_slide(self, *a, **kw): return await out_repo.update_outline_slide(self.db, *a, **kw)
    async def update_outline_slide_index(self, *a, **kw): return await out_repo.update_outline_slide_index(self.db, *a, **kw)
    async def update_outline_slide_citations(self, *a, **kw): return await out_repo.update_outline_slide_citations(self.db, *a, **kw)
    async def update_outline_slide_status(self, *a, **kw): return await out_repo.update_outline_slide_status(self.db, *a, **kw)
    async def delete_outline_slide(self, *a, **kw): return await out_repo.delete_outline_slide(self.db, *a, **kw)
    async def insert_outline_slide_after(self, *a, **kw): return await out_repo.insert_outline_slide_after(self.db, *a, **kw)
    async def replace_outline_slides(self, *a, **kw): return await out_repo.replace_outline_slides(self.db, *a, **kw)
    # outline_section
    async def create_outline_section(self, *a, **kw): return await out_repo.create_outline_section(self.db, *a, **kw)
    async def get_outline_section(self, *a, **kw): return await out_repo.get_outline_section(self.db, *a, **kw)
    async def get_sections_by_outline_id(self, *a, **kw): return await out_repo.get_sections_by_outline_id(self.db, *a, **kw)
    async def update_outline_section(self, *a, **kw): return await out_repo.update_outline_section(self.db, *a, **kw)
    async def delete_outline_section(self, *a, **kw): return await out_repo.delete_outline_section(self.db, *a, **kw)

    # ─── ppt ───
    async def create_presentation(self, *a, **kw): return await ppt_repo.create_presentation(self.db, *a, **kw)
    async def get_presentation(self, *a, **kw): return await ppt_repo.get_presentation(self.db, *a, **kw)
    async def list_presentations_by_conversation(self, *a, **kw): return await ppt_repo.list_presentations_by_conversation(self.db, *a, **kw)
    async def list_presentations_by_user(self, *a, **kw): return await ppt_repo.list_presentations_by_user(self.db, *a, **kw)
    async def update_presentation_status(self, *a, **kw): return await ppt_repo.update_presentation_status(self.db, *a, **kw)
    async def set_presentation_style(self, *a, **kw): return await ppt_repo.set_presentation_style(self.db, *a, **kw)
    async def set_presentation_output(self, *a, **kw): return await ppt_repo.set_presentation_output(self.db, *a, **kw)
    async def soft_delete_presentation(self, *a, **kw): return await ppt_repo.soft_delete_presentation(self.db, *a, **kw)
    # presentation_slide
    async def create_presentation_slide(self, *a, **kw): return await ppt_repo.create_presentation_slide(self.db, *a, **kw)
    async def create_presentation_slides_batch(self, *a, **kw): return await ppt_repo.create_presentation_slides_batch(self.db, *a, **kw)
    async def get_presentation_slide(self, *a, **kw): return await ppt_repo.get_presentation_slide(self.db, *a, **kw)
    async def get_slides_by_presentation_id(self, *a, **kw): return await ppt_repo.get_slides_by_presentation_id(self.db, *a, **kw)
    async def set_slide_agent_output(self, *a, **kw): return await ppt_repo.set_slide_agent_output(self.db, *a, **kw)
    async def update_slide_status(self, *a, **kw): return await ppt_repo.update_slide_status(self.db, *a, **kw)
    async def update_slides_style(self, *a, **kw): return await ppt_repo.update_slides_style(self.db, *a, **kw)
    async def set_slide_chart_data(self, *a, **kw): return await ppt_repo.set_slide_chart_data(self.db, *a, **kw)
    async def set_slide_table_data(self, *a, **kw): return await ppt_repo.set_slide_table_data(self.db, *a, **kw)
    async def set_slide_image_paths(self, *a, **kw): return await ppt_repo.set_slide_image_paths(self.db, *a, **kw)
    async def delete_presentation_slide(self, *a, **kw): return await ppt_repo.delete_presentation_slide(self.db, *a, **kw)
    async def replace_presentation_slides(self, *a, **kw): return await ppt_repo.replace_presentation_slides(self.db, *a, **kw)

    # ─── style ───
    async def create_style(self, *a, **kw): return await style_repo.create_style(self.db, *a, **kw)
    async def get_style(self, *a, **kw): return await style_repo.get_style(self.db, *a, **kw)
    async def search_styles(self, *a, **kw): return await style_repo.search_styles(self.db, *a, **kw)

    # ─── knowledge ───
    async def create_knowledge_file(self, *a, **kw): return await kn_repo.create_knowledge_file(self.db, *a, **kw)
    async def get_knowledge_file(self, *a, **kw): return await kn_repo.get_knowledge_file(self.db, *a, **kw)
    async def list_knowledge_files(self, *a, **kw): return await kn_repo.list_knowledge_files(self.db, *a, **kw)
    async def update_knowledge_file_status(self, *a, **kw): return await kn_repo.update_knowledge_file_status(self.db, *a, **kw)
    async def update_knowledge_file_summary(self, *a, **kw): return await kn_repo.update_knowledge_file_summary(self.db, *a, **kw)
    async def delete_knowledge_file(self, *a, **kw): return await kn_repo.delete_knowledge_file(self.db, *a, **kw)
    # chunks
    async def create_chunk(self, *a, **kw): return await kn_repo.create_chunk(self.db, *a, **kw)
    async def get_chunk_by_id(self, *a, **kw): return await kn_repo.get_chunk_by_id(self.db, *a, **kw)
    async def list_chunks_by_file(self, *a, **kw): return await kn_repo.list_chunks_by_file(self.db, *a, **kw)
    async def get_all_chunks_for_user(self, *a, **kw): return await kn_repo.get_all_chunks_for_user(self.db, *a, **kw)

    # ─── snapshot ───
    async def create_snapshot(self, *a, **kw): return await snap_repo.create_snapshot(self.db, *a, **kw)
    async def get_snapshot(self, *a, **kw): return await snap_repo.get_snapshot(self.db, *a, **kw)
    async def list_snapshots_by_presentation(self, *a, **kw): return await snap_repo.list_snapshots_by_presentation(self.db, *a, **kw)
    async def get_latest_snapshot(self, *a, **kw): return await snap_repo.get_latest_snapshot(self.db, *a, **kw)
    async def delete_snapshot(self, *a, **kw): return await snap_repo.delete_snapshot(self.db, *a, **kw)
    # outline_snapshot
    async def create_outline_snapshot(self, *a, **kw): return await snap_repo.create_outline_snapshot(self.db, *a, **kw)
    async def get_outline_snapshot(self, *a, **kw): return await snap_repo.get_outline_snapshot(self.db, *a, **kw)
    async def list_outline_snapshots(self, *a, **kw): return await snap_repo.list_outline_snapshots(self.db, *a, **kw)
    async def get_latest_outline_snapshot(self, *a, **kw): return await snap_repo.get_latest_outline_snapshot(self.db, *a, **kw)
    async def delete_outline_snapshot(self, *a, **kw): return await snap_repo.delete_outline_snapshot(self.db, *a, **kw)

    # ─── cost ───
    async def cost_summary(self, *a, **kw): return await cost_repo.cost_summary(self.db, *a, **kw)
    async def cost_by_date(self, *a, **kw): return await cost_repo.cost_by_date(self.db, *a, **kw)
    async def cost_by_conversation(self, *a, **kw): return await cost_repo.cost_by_conversation(self.db, *a, **kw)
