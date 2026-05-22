from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Outline, OutlineSlide


# ──────────────────────── Outline ────────────────────────

async def create_outline(
    db: AsyncSession,
    user_id: int,
    conversation_id: int,
    title: str,
    slide_count: int | None = None,
) -> Outline:
    outline = Outline(
        user_id=user_id,
        conversation_id=conversation_id,
        title=title,
        slide_count=slide_count,
    )
    db.add(outline)
    await db.commit()
    await db.refresh(outline)
    return outline


async def get_outline(db: AsyncSession, outline_id: int) -> Outline | None:
    return await db.get(Outline, outline_id)


async def list_outlines(
    db: AsyncSession, conversation_id: int
) -> list[Outline]:
    stmt = (
        select(Outline)
        .where(Outline.conversation_id == conversation_id)
        .order_by(Outline.version.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_outline_status(
    db: AsyncSession, outline_id: int, status: str
) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None:
        return False
    outline.status = status
    await db.commit()
    return True


async def update_outline_eval(
    db: AsyncSession,
    outline_id: int,
    score: float,
    feedback: str,
) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None:
        return False
    outline.eval_score = score
    outline.eval_feedback = feedback
    await db.commit()
    return True


async def set_user_feedback(
    db: AsyncSession, outline_id: int, feedback: str
) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None:
        return False
    outline.user_feedback = feedback
    await db.commit()
    return True


async def increment_outline_version(db: AsyncSession, outline_id: int) -> int | None:
    outline = await db.get(Outline, outline_id)
    if outline is None:
        return None
    outline.version = (outline.version or 1) + 1
    await db.commit()
    return outline.version


async def delete_outline(db: AsyncSession, outline_id: int) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None:
        return False
    await db.delete(outline)
    await db.commit()
    return True


# ──────────────────── OutlineSlide ────────────────────

async def create_outline_slide(
    db: AsyncSession,
    outline_id: int,
    slide_index: int,
    title: str,
    content_json: dict | None = None,
    layout_type: str = "content",
    has_image: bool = False,
    has_chart: bool = False,
    notes: str | None = None,
) -> OutlineSlide:
    slide = OutlineSlide(
        outline_id=outline_id,
        slide_index=slide_index,
        title=title,
        content_json=content_json,
        layout_type=layout_type,
        has_image=has_image,
        has_chart=has_chart,
        notes=notes,
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return slide


async def get_outline_slide(db: AsyncSession, slide_id: int) -> OutlineSlide | None:
    return await db.get(OutlineSlide, slide_id)


async def list_outline_slides(
    db: AsyncSession, outline_id: int
) -> list[OutlineSlide]:
    stmt = (
        select(OutlineSlide)
        .where(OutlineSlide.outline_id == outline_id)
        .order_by(OutlineSlide.slide_index.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_outline_slide(
    db: AsyncSession,
    slide_id: int,
    title: str | None = None,
    content_json: dict | None = None,
    layout_type: str | None = None,
    notes: str | None = None,
) -> bool:
    slide = await db.get(OutlineSlide, slide_id)
    if slide is None:
        return False
    if title is not None:
        slide.title = title
    if content_json is not None:
        slide.content_json = content_json
    if layout_type is not None:
        slide.layout_type = layout_type
    if notes is not None:
        slide.notes = notes
    await db.commit()
    return True


async def delete_outline_slide(db: AsyncSession, slide_id: int) -> bool:
    slide = await db.get(OutlineSlide, slide_id)
    if slide is None:
        return False
    await db.delete(slide)
    await db.commit()
    return True


async def replace_outline_slides(
    db: AsyncSession,
    outline_id: int,
    slides: list[dict],
) -> list[OutlineSlide]:
    """Replace all slides of an outline with a new set."""
    old = await list_outline_slides(db, outline_id)
    for s in old:
        await db.delete(s)
    await db.commit()

    new = []
    for s in slides:
        slide = await create_outline_slide(
            db,
            outline_id=outline_id,
            slide_index=s["slide_index"],
            title=s["title"],
            content_json=s.get("content_json"),
            layout_type=s.get("layout_type", "content"),
            has_image=s.get("has_image", False),
            has_chart=s.get("has_chart", False),
            notes=s.get("notes"),
        )
        new.append(slide)
    return new
