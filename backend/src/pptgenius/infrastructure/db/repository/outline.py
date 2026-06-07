from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Outline, OutlineSection, OutlineSlide


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
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return None
    return outline


async def list_outlines_by_conversation(
    db: AsyncSession, conversation_id: int
) -> list[Outline]:
    stmt = (
        select(Outline)
        .where(Outline.conversation_id == conversation_id)
        .where(Outline.status != "deleted")
        .order_by(Outline.updated_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_outlines_by_user(
    db: AsyncSession, user_id: int, offset: int = 0, limit: int = 20
) -> list[Outline]:
    stmt = (
        select(Outline)
        .where(Outline.user_id == user_id)
        .where(Outline.status != "deleted")
        .order_by(Outline.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_outline_status(
    db: AsyncSession, outline_id: int, status: str
) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return False
    outline.status = status
    await db.commit()
    return True


async def update_outline_eval(
    db: AsyncSession, outline_id: int, score: float, detail: dict | None = None
) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return False
    outline.eval_score = score
    if detail is not None:
        outline.eval_detail = detail
    await db.commit()
    return True


async def increase_outline_version(
    db: AsyncSession,
    outline_id: int,
    type: str, # "major", "minor", or "patch"
) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return False
    if type == "major":
        outline.version_major += 1
        outline.version_minor = 0
        outline.version_patch = 0
    elif type == "minor":
        outline.version_minor += 1
        outline.version_patch = 0
    elif type == "patch":
        outline.version_patch += 1
    await db.commit()
    return True


async def soft_delete_outline(db: AsyncSession, outline_id: int) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None:
        return False
    outline.status = "deleted"
    await db.commit()
    return True


# ──────────────────── OutlineSection ────────────────────

async def create_outline_section(
    db: AsyncSession,
    outline_id: int,
    section_index: int,
    title: str,
    description: str | None = None,
) -> OutlineSection:
    section = OutlineSection(
        outline_id=outline_id,
        section_index=section_index,
        title=title,
        description=description,
    )
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return section


async def get_outline_section(db: AsyncSession, section_id: int) -> OutlineSection | None:
    return await db.get(OutlineSection, section_id)


async def get_sections_by_outline_id(
    db: AsyncSession, outline_id: int
) -> list[OutlineSection]:
    stmt = (
        select(OutlineSection)
        .where(OutlineSection.outline_id == outline_id)
        .order_by(OutlineSection.section_index.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_outline_section(
    db: AsyncSession,
    section_id: int,
    title: str | None = None,
    description: str | None = None,
    slide_count: int | None = None,
) -> bool:
    section = await db.get(OutlineSection, section_id)
    if section is None:
        return False
    if title is not None:
        section.title = title
    if description is not None:
        section.description = description
    if slide_count is not None:
        section.slide_count = slide_count
    await db.commit()
    return True


async def delete_outline_section(db: AsyncSession, section_id: int) -> bool:
    section = await db.get(OutlineSection, section_id)
    if section is None:
        return False
    await db.delete(section)
    await db.commit()
    return True


# ──────────────────── OutlineSlide ────────────────────

async def create_outline_slide(
    db: AsyncSession,
    outline_id: int,
    slide_index: int,
    title: str,
    section_id: int | None = None,
    content_json: dict | None = None,
    layout_type: str = "content",
    has_image: bool = False,
    has_chart: bool = False,
    notes: str | None = None,
) -> OutlineSlide:
    slide = OutlineSlide(
        outline_id=outline_id,
        section_id=section_id,
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


async def get_slides_by_outline_id(
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
    status: str | None = None,
    section_id: int | None = None,
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
    if status is not None:
        slide.status = status
    if section_id is not None:
        slide.section_id = section_id
    await db.commit()
    return True


async def update_outline_slide_index(
    db: AsyncSession, slide_id: int, new_index: int
) -> bool:
    slide = await db.get(OutlineSlide, slide_id)
    if slide is None:
        return False
    if new_index < 1:
        return False
    slide.slide_index = new_index
    await db.commit()
    return True


async def update_outline_slide_citations(
    db: AsyncSession, slide_id: int, citations: list
) -> bool:
    slide = await db.get(OutlineSlide, slide_id)
    if slide is None:
        return False
    slide.citations = citations
    await db.commit()
    return True


async def update_outline_slide_status(
    db: AsyncSession, slide_id: int, status: str
) -> bool:
    slide = await db.get(OutlineSlide, slide_id)
    if slide is None:
        return False
    slide.status = status
    await db.commit()
    return True


async def delete_outline_slide(db: AsyncSession, slide_id: int) -> bool:
    """Delete a slide and decrement all higher-indexed slides in the same outline."""
    slide = await db.get(OutlineSlide, slide_id)
    if slide is None:
        return False
    outline_id = slide.outline_id
    deleted_index = slide.slide_index
    await db.delete(slide)
    await db.flush()
    # Shift all slides with index > deleted_index down by 1
    from sqlalchemy import update
    await db.execute(
        update(OutlineSlide)
        .where(OutlineSlide.outline_id == outline_id)
        .where(OutlineSlide.slide_index > deleted_index)
        .values(slide_index=OutlineSlide.slide_index - 1)
    )
    await db.commit()
    return True


async def insert_outline_slide_after(
    db: AsyncSession,
    outline_id: int,
    after_slide_id: int,
    title: str,
    section_id: int | None = None,
    content_json: dict | None = None,
    layout_type: str = "content",
    notes: str | None = None,
) -> OutlineSlide:
    """Insert a slide after the slide identified by *after_slide_id*.

    All slides with index > the reference slide's index are shifted up by 1.
    The new slide gets index = reference.index + 1.
    """
    from sqlalchemy import update
    ref = await db.get(OutlineSlide, after_slide_id)
    if ref is None:
        raise ValueError(f"Reference slide {after_slide_id} not found")
    after_index = ref.slide_index
    new_index = after_index + 1
    await db.execute(
        update(OutlineSlide)
        .where(OutlineSlide.outline_id == outline_id)
        .where(OutlineSlide.slide_index > after_index)
        .values(slide_index=OutlineSlide.slide_index + 1)
    )
    await db.flush()
    slide = OutlineSlide(
        outline_id=outline_id,
        section_id=section_id,
        slide_index=new_index,
        title=title,
        content_json=content_json,
        layout_type=layout_type,
        notes=notes,
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return slide


async def replace_outline_slides(
    db: AsyncSession,
    outline_id: int,
    slides: list[dict],
) -> list[OutlineSlide]:
    old = await get_slides_by_outline_id(db, outline_id)
    for s in old:
        await db.delete(s)
    await db.commit()

    new = []
    for s in slides:
        slide = await create_outline_slide(
            db,
            outline_id=outline_id,
            section_id=s.get("section_id"),
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
