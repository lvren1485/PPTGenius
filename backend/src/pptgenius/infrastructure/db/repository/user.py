from sqlalchemy import select, update
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


async def get_user_by_name(db: AsyncSession, name: str) -> User | None:
    result = await db.execute(select(User).where(User.name == name))
    return result.scalar_one_or_none()


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


async def update_user_other(db: AsyncSession, user_id: int, other: dict) -> bool:
    u = await db.get(User, user_id)
    if u is None:
        return False
    u.other = other
    await db.commit()
    return True


async def get_rag_mode(db: AsyncSession, user_id: int) -> str:
    """Read rag_mode from users.other. Defaults to 'user'."""
    u = await db.get(User, user_id)
    if u is None:
        return "user"
    return (u.other or {}).get("rag_mode", "user")


async def set_rag_mode(db: AsyncSession, user_id: int, mode: str) -> bool:
    """Set rag_mode in users.other ('user' or 'conversation')."""
    if mode not in ("user", "conversation"):
        return False
    u = await db.get(User, user_id)
    if u is None:
        return False
    other = dict(u.other or {})
    other["rag_mode"] = mode
    u.other = other
    await db.commit()
    return True
