from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation, Message
import time as _time


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
    token_cost_json: dict | None = None,
    created_at: float | None = _time.time(),
) -> Message:
    from datetime import datetime as _dt
    idx = await _get_next_idx(db, conversation_id)
    kwargs = dict(
        conversation_id=conversation_id,
        idx=idx,
        role=role,
        content=content,
        content_type=content_type,
        estimated_cost=estimated_cost,
        metadata_json=metadata_json,
        token_cost_json=token_cost_json,
    )
    if created_at is not None:
        kwargs["created_at"] = _dt.fromtimestamp(created_at)
    msg = Message(**kwargs)
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


async def create_document_message(
    db: AsyncSession,
    conversation_id: int,
    doc_type: str,
    doc_data: dict,
    content: str = "",
) -> Message:
    """Create a document-type message (outline / ppt).  Not fed into LLM history."""
    idx = await _get_next_idx(db, conversation_id)
    msg = Message(
        conversation_id=conversation_id,
        idx=idx,
        role="document",
        content=content,
        content_type=doc_type,       # "outline" or "ppt"
        metadata_json=doc_data,      # {outline_id: N, title: "..."} or {presentation_id: N, title: "..."}
        estimated_cost=None,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def update_message_token_cost(
    db: AsyncSession, message_id: int, cost: dict
) -> bool:
    msg = await db.get(Message, message_id)
    if msg is None:
        return False
    current = dict(msg.token_cost_json or {})
    for k, v in cost.items():
        current[k] = current.get(k, 0) + v
    msg.token_cost_json = current
    await db.commit()
    return True


async def set_message_cost(
    db: AsyncSession,
    message_id: int,
    token_cost_json: dict,
    estimated_cost: float,
) -> bool:
    """Set both token_cost_json and estimated_cost on a message, and accumulate
    estimated_cost to the conversation."""
    msg = await db.get(Message, message_id)
    if msg is None:
        return False
    msg.token_cost_json = token_cost_json
    msg.estimated_cost = estimated_cost
    await db.commit()
    await _add_conversation_cost(db, msg.conversation_id, estimated_cost)
    return True


async def trim_messages(db: AsyncSession, conversation_id: int, before_idx: int) -> int:
    from sqlalchemy import delete

    stmt = (
        delete(Message)
        .where(Message.conversation_id == conversation_id)
        .where(Message.idx < before_idx)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount
