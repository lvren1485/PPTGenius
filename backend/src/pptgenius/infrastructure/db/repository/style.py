from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Style


async def create_style(
    db: AsyncSession,
    name: str,
    label: str,
    colors_json: dict,
    chart_colors_json: dict,
    fonts_json: dict,
    style_density: str = "moderate",
    decoration_json: dict | None = None,
    background_json: dict | None = None,
) -> Style:
    s = Style(
        name=name,
        label=label,
        colors_json=colors_json,
        chart_colors_json=chart_colors_json,
        fonts_json=fonts_json,
        style_density=style_density,
        decoration_json=decoration_json or {},
        background_json=background_json,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def search_styles(
    db: AsyncSession, query: str, limit: int = 20
) -> list[Style]:
    """Fuzzy search on name + label fields. Only active styles."""
    pattern = f"%{query}%"
    stmt = (
        select(Style)
        .where(Style.is_active == True)
        .where(
            Style.name.ilike(pattern) | Style.label.ilike(pattern)
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_style(db: AsyncSession, style_id: int) -> Style | None:
    return await db.get(Style, style_id)
