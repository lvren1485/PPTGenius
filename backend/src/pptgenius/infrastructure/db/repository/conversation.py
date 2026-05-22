from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation


async def create_conversation(
    db: AsyncSession, user_id: int, title: str = "", workspace_path: str = ""
) -> Conversation:
    conv = Conversation(user_id=user_id, title=title, workspace_path=workspace_path)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_conversation(db: AsyncSession, conv_id: int) -> Conversation | None:
    return await db.get(Conversation, conv_id)


async def list_conversations(
    db: AsyncSession, user_id: int, status: str | None = None, offset: int = 0, limit: int = 20
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.user_id == user_id)
    if status:
        stmt = stmt.where(Conversation.status == status)
    stmt = stmt.order_by(Conversation.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_conversation_title(db: AsyncSession, conv_id: int, title: str) -> bool:
    conv = await db.get(Conversation, conv_id)
    if conv is None:
        return False
    conv.title = title
    await db.commit()
    return True


async def update_conversation_phase(
    db: AsyncSession, conv_id: int, phase: str
) -> bool:
    conv = await db.get(Conversation, conv_id)
    if conv is None:
        return False
    conv.current_phase = phase
    await db.commit()
    return True


async def add_tokens(db: AsyncSession, conv_id: int, tokens: int) -> bool:
    conv = await db.get(Conversation, conv_id)
    if conv is None:
        return False
    conv.total_tokens = (conv.total_tokens or 0) + tokens
    await db.commit()
    return True


async def archive_conversation(db: AsyncSession, conv_id: int) -> bool:
    conv = await db.get(Conversation, conv_id)
    if conv is None:
        return False
    conv.status = "archived"
    await db.commit()
    return True


async def delete_conversation(db: AsyncSession, conv_id: int) -> bool:
    conv = await db.get(Conversation, conv_id)
    if conv is None:
        return False
    await db.delete(conv)
    await db.commit()
    return True
