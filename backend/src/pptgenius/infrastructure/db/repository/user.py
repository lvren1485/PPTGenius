from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User


async def create_user(db: AsyncSession, name: str = "default") -> User:
    user = User(name=name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_or_create_default_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        user = await create_user(db)
    return user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    user = await db.get(User, user_id)
    if user is None:
        return False
    await db.delete(user)
    await db.commit()
    return True
