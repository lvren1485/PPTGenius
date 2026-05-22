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
    return await db.get(Presentation, pres_id)


async def list_presentations(
    db: AsyncSession, conversation_id: int
) -> list[Presentation]:
    stmt = (
        select(Presentation)
        .where(Presentation.conversation_id == conversation_id)
        .order_by(Presentation.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_presentation_status(
    db: AsyncSession, pres_id: int, status: str, error_msg: str | None = None
) -> bool:
    pres = await db.get(Presentation, pres_id)
    if pres is None:
        return False
    pres.status = status
    if error_msg is not None:
        pres.error_msg = error_msg
    await db.commit()
    return True


async def delete_presentation(db: AsyncSession, pres_id: int) -> bool:
    pres = await db.get(Presentation, pres_id)
    if pres is None:
        return False
    await db.delete(pres)
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


async def list_presentation_slides(
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
    old = await list_presentation_slides(db, presentation_id)
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
