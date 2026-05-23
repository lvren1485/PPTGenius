from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Presentation, PresentationSlide


# ──────────────────── Presentation ────────────────────

async def create_presentation(
    db: AsyncSession,
    user_id: int,
    conversation_id: int,
    file_path: str,
    outline_id: int | None = None,
    file_size: int | None = None,
    slide_count: int | None = None,
) -> Presentation:
    pres = Presentation(
        user_id=user_id,
        conversation_id=conversation_id,
        outline_id=outline_id,
        file_path=file_path,
        file_size=file_size,
        slide_count=slide_count,
    )
    db.add(pres)
    await db.commit()
    await db.refresh(pres)
    return pres


async def get_presentation(db: AsyncSession, pres_id: int) -> Presentation | None:
    pres = await db.get(Presentation, pres_id)
    if pres is None or pres.status == "deleted":
        return None
    return pres


async def list_presentations_by_conversation(
    db: AsyncSession, conversation_id: int
) -> list[Presentation]:
    stmt = (
        select(Presentation)
        .where(Presentation.conversation_id == conversation_id)
        .where(Presentation.status != "deleted")
        .order_by(Presentation.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_presentations_by_user(
    db: AsyncSession, user_id: int, offset: int = 0, limit: int = 20
) -> list[Presentation]:
    stmt = (
        select(Presentation)
        .where(Presentation.user_id == user_id)
        .where(Presentation.status != "deleted")
        .order_by(Presentation.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_presentation_status(
    db: AsyncSession, pres_id: int, status: str, error_msg: str | None = None
) -> bool:
    pres = await db.get(Presentation, pres_id)
    if pres is None or pres.status == "deleted":
        return False
    pres.status = status
    if error_msg is not None:
        pres.error_msg = error_msg
    await db.commit()
    return True


async def soft_delete_presentation(db: AsyncSession, pres_id: int) -> bool:
    pres = await db.get(Presentation, pres_id)
    if pres is None:
        return False
    pres.status = "deleted"
    await db.commit()
    return True


# ──────────────── PresentationSlide ────────────────

async def create_presentation_slide(
    db: AsyncSession,
    presentation_id: int,
    slide_index: int,
    layout_type: str,
    color_scheme: dict | None = None,
    text_content_json: dict | None = None,
    image_paths: str | None = None,
    chart_paths: str | None = None,
) -> PresentationSlide:
    slide = PresentationSlide(
        presentation_id=presentation_id,
        slide_index=slide_index,
        layout_type=layout_type,
        color_scheme=color_scheme,
        text_content_json=text_content_json,
        image_paths=image_paths,
        chart_paths=chart_paths,
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return slide


async def get_presentation_slide(
    db: AsyncSession, slide_id: int
) -> PresentationSlide | None:
    return await db.get(PresentationSlide, slide_id)


async def get_slides_by_presentation_id(
    db: AsyncSession, presentation_id: int
) -> list[PresentationSlide]:
    stmt = (
        select(PresentationSlide)
        .where(PresentationSlide.presentation_id == presentation_id)
        .order_by(PresentationSlide.slide_index.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_presentation_slide(db: AsyncSession, slide_id: int) -> bool:
    slide = await db.get(PresentationSlide, slide_id)
    if slide is None:
        return False
    await db.delete(slide)
    await db.commit()
    return True


async def replace_presentation_slides(
    db: AsyncSession,
    presentation_id: int,
    slides: list[dict],
) -> list[PresentationSlide]:
    old = await get_slides_by_presentation_id(db, presentation_id)
    for s in old:
        await db.delete(s)
    await db.commit()

    new = []
    for s in slides:
        slide = await create_presentation_slide(
            db,
            presentation_id=presentation_id,
            slide_index=s["slide_index"],
            layout_type=s["layout_type"],
            color_scheme=s.get("color_scheme"),
            text_content_json=s.get("text_content_json"),
            image_paths=s.get("image_paths"),
            chart_paths=s.get("chart_paths"),
        )
        new.append(slide)
    return new
