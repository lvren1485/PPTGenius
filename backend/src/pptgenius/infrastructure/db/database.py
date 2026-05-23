"""Database 薄包装 — 持有 AsyncSession，自动传入 db 参数给各 repository 函数."""

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import (
    conversation as conv_repo,
    knowledge as kn_repo,
    message as msg_repo,
    snapshot as snap_repo,
    outline as out_repo,
    ppt as ppt_repo,
    template as tpl_repo,
    user as user_repo,
    web_resource as wr_repo,
)


class Database:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── user ───
    async def create_user(self, *a, **kw): return await user_repo.create_user(self.db, *a, **kw)
    async def get_user(self, *a, **kw): return await user_repo.get_user(self.db, *a, **kw)
    async def get_or_create_default_user(self): return await user_repo.get_or_create_default_user(self.db)
    async def delete_user(self, *a, **kw): return await user_repo.delete_user(self.db, *a, **kw)

    # ─── conversation ───
    async def create_conversation(self, *a, **kw): return await conv_repo.create_conversation(self.db, *a, **kw)
    async def get_conversation(self, *a, **kw): return await conv_repo.get_conversation(self.db, *a, **kw)
    async def list_conversations(self, *a, **kw): return await conv_repo.list_conversations(self.db, *a, **kw)
    async def update_conversation_title(self, *a, **kw): return await conv_repo.update_conversation_title(self.db, *a, **kw)
    async def update_conversation_phase(self, *a, **kw): return await conv_repo.update_conversation_phase(self.db, *a, **kw)
    async def soft_delete_conversation(self, *a, **kw): return await conv_repo.soft_delete_conversation(self.db, *a, **kw)

    # ─── message ───
    async def create_message(self, *a, **kw): return await msg_repo.create_message(self.db, *a, **kw)
    async def create_human_message(self, *a, **kw): return await msg_repo.create_human_message(self.db, *a, **kw)
    async def get_messages_by_conversation(self, *a, **kw): return await msg_repo.get_messages_by_conversation(self.db, *a, **kw)
    async def trim_messages(self, *a, **kw): return await msg_repo.trim_messages(self.db, *a, **kw)

    # ─── outline ───
    async def create_outline(self, *a, **kw): return await out_repo.create_outline(self.db, *a, **kw)
    async def get_outline(self, *a, **kw): return await out_repo.get_outline(self.db, *a, **kw)
    async def list_outlines_by_conversation(self, *a, **kw): return await out_repo.list_outlines_by_conversation(self.db, *a, **kw)
    async def list_outlines_by_user(self, *a, **kw): return await out_repo.list_outlines_by_user(self.db, *a, **kw)
    async def update_outline_status(self, *a, **kw): return await out_repo.update_outline_status(self.db, *a, **kw)
    async def update_outline_eval(self, *a, **kw): return await out_repo.update_outline_eval(self.db, *a, **kw)
    async def increment_outline_version(self, *a, **kw): return await out_repo.increment_outline_version(self.db, *a, **kw)
    async def soft_delete_outline(self, *a, **kw): return await out_repo.soft_delete_outline(self.db, *a, **kw)
    # outline_slide
    async def create_outline_slide(self, *a, **kw): return await out_repo.create_outline_slide(self.db, *a, **kw)
    async def get_outline_slide(self, *a, **kw): return await out_repo.get_outline_slide(self.db, *a, **kw)
    async def get_slides_by_outline_id(self, *a, **kw): return await out_repo.get_slides_by_outline_id(self.db, *a, **kw)
    async def update_outline_slide(self, *a, **kw): return await out_repo.update_outline_slide(self.db, *a, **kw)
    async def delete_outline_slide(self, *a, **kw): return await out_repo.delete_outline_slide(self.db, *a, **kw)
    async def replace_outline_slides(self, *a, **kw): return await out_repo.replace_outline_slides(self.db, *a, **kw)

    # ─── ppt ───
    async def create_presentation(self, *a, **kw): return await ppt_repo.create_presentation(self.db, *a, **kw)
    async def get_presentation(self, *a, **kw): return await ppt_repo.get_presentation(self.db, *a, **kw)
    async def list_presentations_by_conversation(self, *a, **kw): return await ppt_repo.list_presentations_by_conversation(self.db, *a, **kw)
    async def list_presentations_by_user(self, *a, **kw): return await ppt_repo.list_presentations_by_user(self.db, *a, **kw)
    async def update_presentation_status(self, *a, **kw): return await ppt_repo.update_presentation_status(self.db, *a, **kw)
    async def set_presentation_output(self, *a, **kw): return await ppt_repo.set_presentation_output(self.db, *a, **kw)
    async def soft_delete_presentation(self, *a, **kw): return await ppt_repo.soft_delete_presentation(self.db, *a, **kw)
    # presentation_slide
    async def create_presentation_slide(self, *a, **kw): return await ppt_repo.create_presentation_slide(self.db, *a, **kw)
    async def get_presentation_slide(self, *a, **kw): return await ppt_repo.get_presentation_slide(self.db, *a, **kw)
    async def get_slides_by_presentation_id(self, *a, **kw): return await ppt_repo.get_slides_by_presentation_id(self.db, *a, **kw)
    async def set_slide_agent_output(self, *a, **kw): return await ppt_repo.set_slide_agent_output(self.db, *a, **kw)
    async def update_slide_status(self, *a, **kw): return await ppt_repo.update_slide_status(self.db, *a, **kw)
    async def increment_slide_retry(self, *a, **kw): return await ppt_repo.increment_slide_retry(self.db, *a, **kw)
    async def set_slide_chart_data(self, *a, **kw): return await ppt_repo.set_slide_chart_data(self.db, *a, **kw)
    async def set_slide_table_data(self, *a, **kw): return await ppt_repo.set_slide_table_data(self.db, *a, **kw)
    async def set_slide_image_paths(self, *a, **kw): return await ppt_repo.set_slide_image_paths(self.db, *a, **kw)
    async def delete_presentation_slide(self, *a, **kw): return await ppt_repo.delete_presentation_slide(self.db, *a, **kw)
    async def replace_presentation_slides(self, *a, **kw): return await ppt_repo.replace_presentation_slides(self.db, *a, **kw)

    # ─── template ───
    async def create_template(self, *a, **kw): return await tpl_repo.create_template(self.db, *a, **kw)
    async def create_color_scheme(self, *a, **kw): return await tpl_repo.create_color_scheme(self.db, *a, **kw)
    async def list_active_templates(self): return await tpl_repo.list_active_templates(self.db)
    async def get_template(self, *a, **kw): return await tpl_repo.get_template(self.db, *a, **kw)
    async def list_active_color_schemes(self): return await tpl_repo.list_active_color_schemes(self.db)
    async def get_color_scheme(self, *a, **kw): return await tpl_repo.get_color_scheme(self.db, *a, **kw)

    # ─── knowledge ───
    async def create_knowledge_file(self, *a, **kw): return await kn_repo.create_knowledge_file(self.db, *a, **kw)
    async def get_knowledge_file(self, *a, **kw): return await kn_repo.get_knowledge_file(self.db, *a, **kw)
    async def list_knowledge_files(self, *a, **kw): return await kn_repo.list_knowledge_files(self.db, *a, **kw)
    async def update_knowledge_file_status(self, *a, **kw): return await kn_repo.update_knowledge_file_status(self.db, *a, **kw)
    async def delete_knowledge_file(self, *a, **kw): return await kn_repo.delete_knowledge_file(self.db, *a, **kw)
    # chunks
    async def create_chunk(self, *a, **kw): return await kn_repo.create_chunk(self.db, *a, **kw)
    async def get_chunk_by_id(self, *a, **kw): return await kn_repo.get_chunk_by_id(self.db, *a, **kw)
    async def list_chunks_by_file(self, *a, **kw): return await kn_repo.list_chunks_by_file(self.db, *a, **kw)
    async def get_all_chunks_for_user(self, *a, **kw): return await kn_repo.get_all_chunks_for_user(self.db, *a, **kw)

    # ─── web_resource ───
    async def create_web_resource(self, *a, **kw): return await wr_repo.create_web_resource(self.db, *a, **kw)
    async def get_web_resource(self, *a, **kw): return await wr_repo.get_web_resource(self.db, *a, **kw)
    async def find_web_resource_by_url(self, *a, **kw): return await wr_repo.find_by_url(self.db, *a, **kw)
    async def get_all_web_resources(self, *a, **kw): return await wr_repo.get_all_web_resources(self.db, *a, **kw)
    async def delete_web_resource(self, *a, **kw): return await wr_repo.delete_web_resource(self.db, *a, **kw)

    # ─── snapshot ───
    async def create_snapshot(self, *a, **kw): return await snap_repo.create_snapshot(self.db, *a, **kw)
    async def get_snapshot(self, *a, **kw): return await snap_repo.get_snapshot(self.db, *a, **kw)
    async def list_snapshots_by_presentation(self, *a, **kw): return await snap_repo.list_snapshots_by_presentation(self.db, *a, **kw)
    async def get_latest_snapshot(self, *a, **kw): return await snap_repo.get_latest_snapshot(self.db, *a, **kw)
    async def delete_snapshot(self, *a, **kw): return await snap_repo.delete_snapshot(self.db, *a, **kw)
