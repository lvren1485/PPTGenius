from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User


async def create_user(
    db: AsyncSession,
    name: str = "default",
    password: str = "",
    other: dict | None = None
) -> User:
    u = User(
        name=name,
        password=password,
        other=other,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_or_create_default_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).limit(1))
    u = result.scalar_one_or_none()
    if u is None:
        u = await create_user(db)
    return u


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    u = await db.get(User, user_id)
    if u is None:
        return False
    await db.delete(u)
    await db.commit()
    return True
