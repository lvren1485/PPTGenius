from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Message


async def create_message(
    db: AsyncSession,
    conversation_id: int,
    role: str,
    content: str,
    content_type: str = "text",
    token_count: int | None = None,
    metadata_json: dict | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        content_type=content_type,
        token_count=token_count,
        metadata_json=metadata_json,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_message(db: AsyncSession, msg_id: int) -> Message | None:
    return await db.get(Message, msg_id)


async def list_messages(
    db: AsyncSession,
    conversation_id: int,
    offset: int = 0,
    limit: int = 100,
) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_messages(db: AsyncSession, conversation_id: int) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).where(Message.conversation_id == conversation_id)
    result = await db.execute(stmt)
    return result.scalar_one()


async def delete_message(db: AsyncSession, msg_id: int) -> bool:
    msg = await db.get(Message, msg_id)
    if msg is None:
        return False
    await db.delete(msg)
    await db.commit()
    return True
