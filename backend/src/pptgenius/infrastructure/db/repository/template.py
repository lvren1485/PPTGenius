from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ColorScheme, Template


async def create_template(
    db: AsyncSession,
    name: str,
    label: str,
    layouts_json: dict,
    category: str | None = None,
    description: str | None = None,
    slide_width: float = 13.333,
    slide_height: float = 7.5,
) -> Template:
    t = Template(
        name=name,
        label=label,
        layouts_json=layouts_json,
        category=category,
        description=description,
        slide_width=slide_width,
        slide_height=slide_height,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def create_color_scheme(
    db: AsyncSession,
    name: str,
    label: str,
    colors_json: dict,
    chart_colors_json: dict,
    fonts_json: dict,
) -> ColorScheme:
    cs = ColorScheme(
        name=name,
        label=label,
        colors_json=colors_json,
        chart_colors_json=chart_colors_json,
        fonts_json=fonts_json,
    )
    db.add(cs)
    await db.commit()
    await db.refresh(cs)
    return cs


async def list_active_templates(db: AsyncSession) -> list[Template]:
    result = await db.execute(select(Template).where(Template.is_active == True))
    return list(result.scalars().all())


async def get_template(db: AsyncSession, template_id: int) -> Template | None:
    return await db.get(Template, template_id)


async def list_active_color_schemes(db: AsyncSession) -> list[ColorScheme]:
    result = await db.execute(select(ColorScheme).where(ColorScheme.is_active == True))
    return list(result.scalars().all())


async def get_color_scheme(db: AsyncSession, cs_id: int) -> ColorScheme | None:
    return await db.get(ColorScheme, cs_id)
