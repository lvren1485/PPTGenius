from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KnowledgeChunk, KnowledgeFile


# ──────────────────── KnowledgeFile ────────────────────

async def create_knowledge_file(
    db: AsyncSession,
    user_id: int,
    filename: str,
    file_path: str,
    file_type: str,
    file_size: int | None = None,
    source_type: str = "upload",
    content_hash: str | None = None,
) -> KnowledgeFile:
    kf = KnowledgeFile(
        user_id=user_id,
        filename=filename,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        source_type=source_type,
        content_hash=content_hash,
    )
    db.add(kf)
    await db.commit()
    await db.refresh(kf)
    return kf


async def get_knowledge_file(db: AsyncSession, file_id: int) -> KnowledgeFile | None:
    return await db.get(KnowledgeFile, file_id)


async def list_knowledge_files(
    db: AsyncSession,
    user_id: int,
    file_type: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
) -> list[KnowledgeFile]:
    stmt = select(KnowledgeFile).where(KnowledgeFile.user_id == user_id)
    if file_type:
        stmt = stmt.where(KnowledgeFile.file_type == file_type)
    if source_type:
        stmt = stmt.where(KnowledgeFile.source_type == source_type)
    if status:
        stmt = stmt.where(KnowledgeFile.status == status)
    stmt = stmt.order_by(KnowledgeFile.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def find_by_hash(db: AsyncSession, content_hash: str) -> KnowledgeFile | None:
    stmt = select(KnowledgeFile).where(KnowledgeFile.content_hash == content_hash)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_knowledge_file_status(
    db: AsyncSession, file_id: int, status: str, chunk_count: int | None = None
) -> bool:
    kf = await db.get(KnowledgeFile, file_id)
    if kf is None:
        return False
    kf.status = status
    if chunk_count is not None:
        kf.chunk_count = chunk_count
    await db.commit()
    return True


async def delete_knowledge_file(db: AsyncSession, file_id: int) -> bool:
    kf = await db.get(KnowledgeFile, file_id)
    if kf is None:
        return False
    await db.delete(kf)
    await db.commit()
    return True


# ────────────────── KnowledgeChunk ──────────────────

async def create_chunk(
    db: AsyncSession,
    file_id: int,
    chunk_index: int,
    chunk_text: str,
    token_count: int | None = None,
) -> KnowledgeChunk:
    chunk = KnowledgeChunk(
        file_id=file_id,
        chunk_index=chunk_index,
        chunk_text=chunk_text,
        token_count=token_count,
    )
    db.add(chunk)
    await db.commit()
    await db.refresh(chunk)
    return chunk


async def list_chunks(
    db: AsyncSession, file_id: int
) -> list[KnowledgeChunk]:
    stmt = (
        select(KnowledgeChunk)
        .where(KnowledgeChunk.file_id == file_id)
        .order_by(KnowledgeChunk.chunk_index.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_all_chunks(db: AsyncSession) -> list[KnowledgeChunk]:
    """获取所有用户的所有 chunk，用于 BM25 索引重建."""
    result = await db.execute(select(KnowledgeChunk))
    return list(result.scalars().all())


async def delete_chunks_by_file(db: AsyncSession, file_id: int) -> int:
    chunks = await list_chunks(db, file_id)
    for c in chunks:
        await db.delete(c)
    await db.commit()
    return len(chunks)
