from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import WebResource


async def create_web_resource(
    db: AsyncSession,
    user_id: int,
    url: str,
    title: str | None = None,
    content_text: str | None = None,
    source_domain: str | None = None,
    stored_path: str | None = None,
) -> WebResource:
    wr = WebResource(
        user_id=user_id,
        url=url,
        title=title,
        content_text=content_text,
        source_domain=source_domain,
        stored_path=stored_path,
    )
    db.add(wr)
    await db.commit()
    await db.refresh(wr)
    return wr


async def get_web_resource(db: AsyncSession, wr_id: int) -> WebResource | None:
    return await db.get(WebResource, wr_id)


async def find_by_url(db: AsyncSession, url: str) -> WebResource | None:
    stmt = select(WebResource).where(WebResource.url == url)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_web_resources(db: AsyncSession, user_id: int) -> list[WebResource]:
    """获取某用户所有 web resource，供 BM25 索引使用。"""
    stmt = (
        select(WebResource)
        .where(WebResource.user_id == user_id)
        .order_by(WebResource.fetched_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_web_resource(db: AsyncSession, wr_id: int) -> bool:
    wr = await db.get(WebResource, wr_id)
    if wr is None:
        return False
    await db.delete(wr)
    await db.commit()
    return True
