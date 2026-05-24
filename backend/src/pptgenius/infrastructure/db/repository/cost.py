"""Cost aggregation queries — grouped by date or conversation."""

from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation, Message


def _days_ago(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


async def cost_summary(db: AsyncSession, user_id: int, days: int = 30) -> dict:
    since = _days_ago(days)
    stmt = (
        select(
            func.coalesce(func.sum(Conversation.estimated_cost), 0).label("total_cost"),
            func.count(Conversation.id).label("total_conversations"),
        )
        .where(Conversation.user_id == user_id)
        .where(Conversation.status != "deleted")
        .where(Conversation.updated_at >= since)
    )
    result = await db.execute(stmt)
    row = result.one()
    total_cost = float(row.total_cost)
    total_conv = row.total_conversations

    msg_stmt = (
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user_id)
        .where(Conversation.status != "deleted")
        .where(Message.created_at >= since)
    )
    total_msgs = (await db.execute(msg_stmt)).scalar_one()

    avg_per_conv = round(total_cost / total_conv, 4) if total_conv else 0.0
    avg_per_day = round(total_cost / days, 4) if days else 0.0

    return {
        "total_cost": round(total_cost, 4),
        "total_conversations": total_conv,
        "total_messages": total_msgs,
        "avg_cost_per_conversation": avg_per_conv,
        "avg_cost_per_day": avg_per_day,
        "days": days,
    }


async def cost_by_date(
    db: AsyncSession, user_id: int, days: int = 30, offset: int = 0, limit: int = 30,
) -> list[dict]:
    since = _days_ago(days)
    stmt = (
        select(
            func.date(Conversation.updated_at).label("dt"),
            func.coalesce(func.sum(Conversation.estimated_cost), 0).label("cost"),
            func.count(Conversation.id).label("conv_count"),
        )
        .where(Conversation.user_id == user_id)
        .where(Conversation.status != "deleted")
        .where(Conversation.updated_at >= since)
        .group_by(text("dt"))
        .order_by(text("dt DESC"))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = []
    for row in result.all():
        date_str = str(row.dt)
        items.append({
            "date": date_str,
            "cost": round(float(row.cost), 4),
            "conversations": row.conv_count,
            "messages": 0,  # filled below
        })

    # Fill message counts per date
    if items:
        msg_stmt = (
            select(
                func.date(Message.created_at).label("dt"),
                func.count(Message.id).label("msg_count"),
            )
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.user_id == user_id)
            .where(Message.created_at >= since)
            .group_by(text("dt"))
        )
        msg_result = await db.execute(msg_stmt)
        msg_counts = {str(row.dt): row.msg_count for row in msg_result.all()}
        for item in items:
            item["messages"] = msg_counts.get(item["date"], 0)

    return items


async def cost_by_conversation(
    db: AsyncSession, user_id: int, days: int = 30, offset: int = 0, limit: int = 20,
) -> list[dict]:
    since = _days_ago(days)
    stmt = (
        select(
            Conversation.id,
            Conversation.title,
            Conversation.estimated_cost,
            func.count(Message.id).label("msg_count"),
            Conversation.created_at,
            Conversation.updated_at,
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user_id)
        .where(Conversation.status != "deleted")
        .where(Conversation.updated_at >= since)
        .group_by(Conversation.id)
        .order_by(Conversation.estimated_cost.desc().nulls_last())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [
        {
            "conversation_id": row.id,
            "title": row.title,
            "cost": round(float(row.estimated_cost or 0), 4),
            "message_count": row.msg_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in result.all()
    ]
