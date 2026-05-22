from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config.settings import RESOURCES_DIR, get_settings

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.db.url, echo=False, pool_size=5)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _sessionmaker


async def create_tables():
    """从 src/resources/schema.sql 执行建表语句."""
    engine = _get_engine()
    schema_path = RESOURCES_DIR / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")

    async with engine.begin() as conn:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("--"):
                await conn.execute(text(stmt))


async def get_db() -> AsyncSession:
    sm = get_sessionmaker()
    async with sm() as session:
        yield session
