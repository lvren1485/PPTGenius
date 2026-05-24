from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation, Message


async def _get_next_idx(db: AsyncSession, conversation_id: int) -> int:
    stmt = (
        select(func.coalesce(func.max(Message.idx), 0))
        .where(Message.conversation_id == conversation_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one() + 1


async def _add_conversation_cost(db: AsyncSession, conversation_id: int, cost: float) -> None:
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        return
    conv.estimated_cost = (conv.estimated_cost or 0) + cost
    await db.commit()


async def create_message(
    db: AsyncSession,
    conversation_id: int,
    role: str,
    content: str,
    content_type: str = "text",
    estimated_cost: float | None = None,
    metadata_json: dict | None = None,
) -> Message:
    """创建消息并自动累加 conversation.estimated_cost。"""
    idx = await _get_next_idx(db, conversation_id)
    msg = Message(
        conversation_id=conversation_id,
        idx=idx,
        role=role,
        content=content,
        content_type=content_type,
        estimated_cost=estimated_cost,
        metadata_json=metadata_json,
    )
    db.add(msg)
    if estimated_cost:
        await _add_conversation_cost(db, conversation_id, estimated_cost)
    await db.commit()
    await db.refresh(msg)
    return msg


async def create_human_message(
    db: AsyncSession,
    conversation_id: int,
    content: str,
) -> Message:
    return await create_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=content,
        content_type="text",
        estimated_cost=0,
    )


async def get_messages_by_conversation(
    db: AsyncSession, conversation_id: int
) -> list[Message]:
    """返回该 conversation 全部消息，按 idx 升序。"""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.idx.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_messages_by_conversation(db: AsyncSession, conversation_id: int) -> int:
    stmt = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    result = await db.execute(stmt)
    return result.scalar_one()


async def trim_messages(db: AsyncSession, conversation_id: int, before_idx: int) -> int:
    """删除 conversation 中 idx 小于 before_idx 的所有消息，返回删除条数。"""
    from sqlalchemy import delete

    stmt = (
        delete(Message)
        .where(Message.conversation_id == conversation_id)
        .where(Message.idx < before_idx)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount
