from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation


async def create_conversation(
    db: AsyncSession, user_id: int, title: str = ""
) -> Conversation:
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    await db.flush()
    conv.workspace_path = f"./data/workspace/{conv.id}"
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_conversation(db: AsyncSession, conv_id: int) -> Conversation | None:
    conv = await db.get(Conversation, conv_id)
    if conv is None:
        return None
    if conv.status == "deleted":
        return None
    return conv


async def list_conversations(
    db: AsyncSession, user_id: int, status: str | None = None, offset: int = 0, limit: int = 20
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .where(Conversation.status != "deleted")
    )
    if status:
        stmt = stmt.where(Conversation.status == status)
    stmt = stmt.order_by(Conversation.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_conversation_title(db: AsyncSession, conv_id: int, title: str) -> bool:
    conv = await db.get(Conversation, conv_id)
    if conv is None or conv.status == "deleted":
        return False
    conv.title = title
    await db.commit()
    return True


async def update_conversation_phase(db: AsyncSession, conv_id: int, phase: str) -> bool:
    conv = await db.get(Conversation, conv_id)
    if conv is None or conv.status == "deleted":
        return False
    conv.current_phase = phase
    await db.commit()
    return True


async def soft_delete_conversation(db: AsyncSession, conv_id: int) -> bool:
    conv = await db.get(Conversation, conv_id)
    if conv is None:
        return False
    conv.status = "deleted"
    await db.commit()
    return True
