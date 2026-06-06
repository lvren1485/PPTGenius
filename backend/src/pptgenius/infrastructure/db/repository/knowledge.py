from sqlalchemy import select
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
    conversation_id: int | None = None,
    web_url: str | None = None,
) -> KnowledgeFile:
    # Check if already exists (common: web fetch duplicate, or concurrent ingest)
    from sqlalchemy import select as _sel
    result = await db.execute(
        _sel(KnowledgeFile).where(KnowledgeFile.file_path == file_path)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    kf = KnowledgeFile(
        user_id=user_id,
        filename=filename,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        source_type=source_type,
        conversation_id=conversation_id,
        web_url=web_url,
    )
    db.add(kf)
    try:
        await db.flush()
        await db.refresh(kf)
        await db.commit()
    except Exception:
        # flush/commit failed (dup key or session conflict) — rollback
        # is unsafe when another flush is in progress, so just query again
        try:
            await db.rollback()
        except Exception:
            pass
        result = await db.execute(
            _sel(KnowledgeFile).where(KnowledgeFile.file_path == file_path)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        # Last attempt: just add + flush
        kf2 = KnowledgeFile(
            user_id=user_id, filename=filename, file_path=file_path,
            file_type=file_type, file_size=file_size, source_type=source_type,
            conversation_id=conversation_id, web_url=web_url,
        )
        db.add(kf2)
        await db.flush()
        await db.refresh(kf2)
        return kf2
    return kf


async def get_knowledge_file(db: AsyncSession, file_id: int) -> KnowledgeFile | None:
    return await db.get(KnowledgeFile, file_id)


async def list_knowledge_files(
    db: AsyncSession,
    user_id: int,
    file_type: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
    conversation_id: int | None = None,
) -> list[KnowledgeFile]:
    stmt = select(KnowledgeFile).where(KnowledgeFile.user_id == user_id)
    if file_type:
        stmt = stmt.where(KnowledgeFile.file_type == file_type)
    if source_type:
        stmt = stmt.where(KnowledgeFile.source_type == source_type)
    if status:
        stmt = stmt.where(KnowledgeFile.status == status)
    if conversation_id is not None:
        stmt = stmt.where(KnowledgeFile.conversation_id == conversation_id)
    stmt = stmt.order_by(KnowledgeFile.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


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


async def update_knowledge_file_summary(
    db: AsyncSession, file_id: int, summary_json: dict
) -> bool:
    kf = await db.get(KnowledgeFile, file_id)
    if kf is None:
        return False
    kf.summary_json = summary_json
    await db.commit()
    return True


async def delete_knowledge_file(db: AsyncSession, file_id: int) -> bool:
    """删除知识文件及其所有 chunks（级联删除）。"""
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


async def get_chunk_by_id(db: AsyncSession, chunk_id: int) -> KnowledgeChunk | None:
    """BM25 检索后 LLM 根据 chunk_id 获取原文。"""
    return await db.get(KnowledgeChunk, chunk_id)


async def list_chunks_by_file(db: AsyncSession, file_id: int) -> list[KnowledgeChunk]:
    stmt = (
        select(KnowledgeChunk)
        .where(KnowledgeChunk.file_id == file_id)
        .order_by(KnowledgeChunk.chunk_index.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_all_chunks_for_user(db: AsyncSession, user_id: int) -> list[KnowledgeChunk]:
    """获取某用户所有 chunk，用于 BM25 索引重建。"""
    stmt = (
        select(KnowledgeChunk)
        .join(KnowledgeFile)
        .where(KnowledgeFile.user_id == user_id)
        .order_by(KnowledgeChunk.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
