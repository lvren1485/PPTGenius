from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import OutlineSnapshot, PresentationSnapshot


async def create_snapshot(
    db: AsyncSession,
    presentation_id: int,
    user_id: int,
    conversation_id: int,
    outline_json: dict,
    presentation_json: dict,
) -> PresentationSnapshot:
    next_version = await _get_next_version(db, presentation_id)
    snap = PresentationSnapshot(
        presentation_id=presentation_id,
        user_id=user_id,
        conversation_id=conversation_id,
        outline_json=outline_json,
        presentation_json=presentation_json,
        version=next_version,
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    return snap


async def _get_next_version(db: AsyncSession, presentation_id: int) -> int:
    stmt = (
        select(func.coalesce(func.max(PresentationSnapshot.version), 0))
        .where(PresentationSnapshot.presentation_id == presentation_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one() + 1


async def get_snapshot(db: AsyncSession, snap_id: int) -> PresentationSnapshot | None:
    return await db.get(PresentationSnapshot, snap_id)


async def list_snapshots_by_presentation(
    db: AsyncSession, presentation_id: int
) -> list[PresentationSnapshot]:
    stmt = (
        select(PresentationSnapshot)
        .where(PresentationSnapshot.presentation_id == presentation_id)
        .order_by(PresentationSnapshot.version.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_latest_snapshot(
    db: AsyncSession, presentation_id: int
) -> PresentationSnapshot | None:
    stmt = (
        select(PresentationSnapshot)
        .where(PresentationSnapshot.presentation_id == presentation_id)
        .order_by(PresentationSnapshot.version.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_snapshot(db: AsyncSession, snap_id: int) -> bool:
    snap = await db.get(PresentationSnapshot, snap_id)
    if snap is None:
        return False
    await db.delete(snap)
    await db.commit()
    return True


# ──────────────────── OutlineSnapshot ────────────────────

async def _get_next_outline_version(db: AsyncSession, outline_id: int) -> int:
    stmt = (
        select(func.coalesce(func.max(OutlineSnapshot.version), 0))
        .where(OutlineSnapshot.outline_id == outline_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one() + 1


async def create_outline_snapshot(
    db: AsyncSession,
    outline_id: int,
    user_id: int,
    conversation_id: int,
    outline_json: dict,
) -> OutlineSnapshot:
    next_version = await _get_next_outline_version(db, outline_id)
    snap = OutlineSnapshot(
        outline_id=outline_id,
        user_id=user_id,
        conversation_id=conversation_id,
        outline_json=outline_json,
        version=next_version,
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    return snap


async def get_outline_snapshot(db: AsyncSession, snap_id: int) -> OutlineSnapshot | None:
    return await db.get(OutlineSnapshot, snap_id)


async def list_outline_snapshots(
    db: AsyncSession, outline_id: int
) -> list[OutlineSnapshot]:
    stmt = (
        select(OutlineSnapshot)
        .where(OutlineSnapshot.outline_id == outline_id)
        .order_by(OutlineSnapshot.version.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_latest_outline_snapshot(
    db: AsyncSession, outline_id: int
) -> OutlineSnapshot | None:
    stmt = (
        select(OutlineSnapshot)
        .where(OutlineSnapshot.outline_id == outline_id)
        .order_by(OutlineSnapshot.version.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_outline_snapshot(db: AsyncSession, snap_id: int) -> bool:
    snap = await db.get(OutlineSnapshot, snap_id)
    if snap is None:
        return False
    await db.delete(snap)
    await db.commit()
    return True
