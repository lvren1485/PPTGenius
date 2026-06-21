from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Outline, OutlineSection, OutlineSlide


# ──────────────────────── Outline ────────────────────────

async def create_outline(
    db: AsyncSession,
    user_id: int,
    conversation_id: int,
    title: str = "",
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


async def set_outline_title(
    db: AsyncSession, outline_id: int, title: str
) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return False
    outline.title = title
    await db.commit()
    return True


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
    db: AsyncSession, outline_id: int
) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return False
    outline.version += 1
    await db.commit()
    return True


async def set_outline_explore_result(
    db: AsyncSession, outline_id: int, explore_result: dict
) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return False
    outline.explore_result_json = explore_result
    await db.commit()
    return True


async def get_outline_explore_result(
    db: AsyncSession, outline_id: int
) -> dict | None:
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return None
    return outline.explore_result_json


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
    citations: dict | None = None,
) -> OutlineSection:
    section = OutlineSection(
        outline_id=outline_id,
        section_index=section_index,
        title=title,
        description=description,
        citations=citations,
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
    citations: dict | None = None,
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
    if citations is not None:
        section.citations = citations
    await db.commit()
    return True


async def soft_delete_outline_section(db: AsyncSession, section_id: int) -> bool:
    """Mark section as deleted."""
    section = await db.get(OutlineSection, section_id)
    if section is None:
        return False
    await db.delete(section)
    await db.commit()
    return True


async def set_outline_slide_count(db: AsyncSession, outline_id: int, count: int) -> bool:
    outline = await db.get(Outline, outline_id)
    if outline is None or outline.status == "deleted":
        return False
    outline.slide_count = count
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
    slide = await db.get(OutlineSlide, slide_id)
    if slide is None or slide.status == "deleted":
        return None
    return slide


async def get_slides_by_outline_id(
    db: AsyncSession, outline_id: int
) -> list[OutlineSlide]:
    stmt = (
        select(OutlineSlide)
        .where(OutlineSlide.outline_id == outline_id)
        .where(OutlineSlide.status != "deleted")
        .order_by(OutlineSlide.slide_index.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def soft_delete_outline_slide(db: AsyncSession, slide_id: int) -> bool:
    slide = await db.get(OutlineSlide, slide_id)
    if slide is None or slide.status == "deleted":
        return False
    slide.status = "deleted"
    slide.slide_index = -slide.id  # unique negative index, avoids unique constraint conflict
    await db.commit()
    return True


async def update_outline_slide(
    db: AsyncSession,
    slide_id: int,
    title: str | None = None,
    content_json: dict | None = None,
    layout_type: str | None = None,
    notes: str | None = None,
    status: str | None = None,
    section_id: int | None = None,
    has_image: bool | None = None,
    has_chart: bool | None = None,
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
    if has_image is not None:
        slide.has_image = has_image
    if has_chart is not None:
        slide.has_chart = has_chart
    await db.commit()
    return True


async def reindex_outline_slides(
    db: AsyncSession, outline_id: int, id_to_index: dict[int, int]
) -> bool:
    """Set slide_index for multiple slides. Two-pass to avoid unique-key conflicts:
    1) Set all to unique negative values (-id), 2) Set to final indices."""
    if not id_to_index:
        return True
    from sqlalchemy import case, update as _up
    ids = list(id_to_index.keys())
    # Pass 1: set to unique negative temp values
    neg_whens = [(OutlineSlide.id == sid, -sid) for sid in ids]
    await db.execute(
        _up(OutlineSlide)
        .where(OutlineSlide.id.in_(ids))
        .values(slide_index=case(*neg_whens, else_=OutlineSlide.slide_index))
    )
    await db.flush()
    # Pass 2: set to final indices
    pos_whens = [(OutlineSlide.id == sid, idx) for sid, idx in id_to_index.items()]
    await db.execute(
        _up(OutlineSlide)
        .where(OutlineSlide.id.in_(ids))
        .values(slide_index=case(*pos_whens, else_=OutlineSlide.slide_index))
    )
    await db.commit()
    return True


async def update_outline_slide_index(
    db: AsyncSession, slide_id: int, new_index: int
) -> bool:
    slide = await db.get(OutlineSlide, slide_id)
    if slide is None:
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
