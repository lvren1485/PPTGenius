from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Presentation, PresentationSlide


# ──────────────────── Presentation ────────────────────

async def create_presentation(
    db: AsyncSession,
    user_id: int,
    conversation_id: int,
    outline_id: int | None = None,
    template_id: int | None = None,
    color_scheme_id: int | None = None,
) -> Presentation:
    pres = Presentation(
        user_id=user_id,
        conversation_id=conversation_id,
        outline_id=outline_id,
        template_id=template_id,
        color_scheme_id=color_scheme_id,
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


async def update_presentation_style(
    db: AsyncSession,
    pres_id: int,
    color_scheme_id: int,
    template_id: int = 1,
) -> bool:
    pres = await db.get(Presentation, pres_id)
    if pres is None or pres.status == "deleted":
        return False
    pres.color_scheme_id = color_scheme_id
    pres.template_id = template_id
    await db.commit()
    return True


async def set_presentation_output(
    db: AsyncSession,
    pres_id: int,
    file_path: str,
    file_size: int,
    slide_count: int,
) -> bool:
    pres = await db.get(Presentation, pres_id)
    if pres is None or pres.status == "deleted":
        return False
    pres.file_path = file_path
    pres.file_size = file_size
    pres.slide_count = slide_count
    pres.status = "completed"
    await db.commit()
    return True


async def soft_delete_presentation(db: AsyncSession, pres_id: int) -> bool:
    pres = await db.get(Presentation, pres_id)
    if pres is None:
        return False
    pres.status = "deleted"
    await db.commit()
    return True


# ─── PresentationSlide ───

async def create_presentation_slide(
    db: AsyncSession,
    presentation_id: int,
    slide_index: int,
    layout_name: str,
    outline_slide_id: int | None = None,
    template_id: int | None = None,
    color_scheme_id: int | None = None,
) -> PresentationSlide:
    s = PresentationSlide(
        presentation_id=presentation_id,
        slide_index=slide_index,
        layout_name=layout_name,
        outline_slide_id=outline_slide_id,
        template_id=template_id,
        color_scheme_id=color_scheme_id,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def create_presentation_slides_batch(
    db: AsyncSession,
    slides: list[dict],
) -> list[PresentationSlide]:
    """Create multiple presentation slides in a single commit."""
    objs = []
    for s in slides:
        obj = PresentationSlide(
            presentation_id=s["presentation_id"],
            slide_index=s["slide_index"],
            layout_name=s["layout_name"],
            outline_slide_id=s.get("outline_slide_id"),
            template_id=s.get("template_id"),
            color_scheme_id=s.get("color_scheme_id"),
        )
        db.add(obj)
        objs.append(obj)
    await db.commit()
    for obj in objs:
        await db.refresh(obj)
    return objs


async def get_presentation_slide(db: AsyncSession, slide_id: int) -> PresentationSlide | None:
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


async def _get_slide(db: AsyncSession, presentation_id: int, slide_index: int):
    """Look up a presentation_slide by (presentation_id, slide_index)."""
    stmt_result = await db.execute(
        select(PresentationSlide)
        .where(PresentationSlide.presentation_id == presentation_id)
        .where(PresentationSlide.slide_index == slide_index)
    )
    return stmt_result.scalar_one_or_none()


async def set_slide_agent_output(
        db: AsyncSession,
        presentation_id: int,
        slide_index: int,
        agent_type: str,
        output: dict,
) -> bool:
    """Accumulative: merges output into agent_outputs[agent_type] without
    overwriting other agent_types.  Safe for concurrent calls from different
    sessions (last-write-wins per key, never deletes other keys)."""
    stmt = (
        select(PresentationSlide)
        .where(PresentationSlide.presentation_id == presentation_id)
        .where(PresentationSlide.slide_index == slide_index)
    )
    result = await db.execute(stmt)
    s = result.scalar_one_or_none()
    if s is None:
        return False
    # Merge into existing: read current + add new key
    current = dict(s.agent_outputs or {})
    current[agent_type] = output
    s.agent_outputs = current
    await db.commit()
    return True


async def update_slides_style(
    db: AsyncSession,
    presentation_id: int,
    color_scheme_id: int,
    template_id: int = 1,
) -> int:
    """Update color_scheme_id and template_id on all slides of a presentation.
    Returns the number of slides updated."""
    from sqlalchemy import update
    stmt = (
        update(PresentationSlide)
        .where(PresentationSlide.presentation_id == presentation_id)
        .values(color_scheme_id=color_scheme_id, template_id=template_id)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount


async def update_slide_status(
    db: AsyncSession,
    presentation_id: int,
    slide_index: int,
    status: str,
    error_message: str | None = None,
) -> bool:
    stmt = (
        select(PresentationSlide)
        .where(PresentationSlide.presentation_id == presentation_id)
        .where(PresentationSlide.slide_index == slide_index)
    )
    result = await db.execute(stmt)
    s = result.scalar_one_or_none()
    if s is None:
        return False
    s.status = status
    if error_message is not None:
        s.error_message = error_message
    await db.commit()
    return True


async def increment_slide_retry(db: AsyncSession, slide_id: int) -> int | None:
    s = await db.get(PresentationSlide, slide_id)
    if s is None:
        return None
    s.retry_count = (s.retry_count or 0) + 1
    await db.commit()
    return s.retry_count


async def set_slide_chart_data(
    db: AsyncSession, presentation_id: int, slide_index: int, chart_data: dict,
) -> bool:
    s = await _get_slide(db, presentation_id, slide_index)
    if s is None:
        return False
    s.chart_data = chart_data
    await db.commit()
    return True


async def set_slide_table_data(
    db: AsyncSession, presentation_id: int, slide_index: int, table_data: dict,
) -> bool:
    s = await _get_slide(db, presentation_id, slide_index)
    if s is None:
        return False
    s.table_data = table_data
    await db.commit()
    return True


async def set_slide_image_paths(
    db: AsyncSession, presentation_id: int, slide_index: int, image_paths: dict,
) -> bool:
    s = await _get_slide(db, presentation_id, slide_index)
    if s is None:
        return False
    s.image_paths = image_paths
    await db.commit()
    return True


async def delete_presentation_slide(db: AsyncSession, slide_id: int) -> bool:
    s = await db.get(PresentationSlide, slide_id)
    if s is None:
        return False
    await db.delete(s)
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
            layout_name=s["layout_name"],
            outline_slide_id=s.get("outline_slide_id"),
            template_id=s.get("template_id"),
            color_scheme_id=s.get("color_scheme_id"),
        )
        new.append(slide)
    return new
