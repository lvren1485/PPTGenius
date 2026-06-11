import logging
import re

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config.settings import RESOURCES_DIR, get_settings

_log = logging.getLogger("pptgenius.db")

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

# MySQL error codes safe to ignore on re-run (idempotent schema)
_DUPLICATE_KEY = 1061


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.db.url, echo=False,
                                       pool_size=25, max_overflow=25,
                                       pool_pre_ping=True, pool_recycle=3600)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _sessionmaker


def _strip_comments(stmt: str) -> str:
    """Remove ``--`` comment lines from a SQL statement."""
    lines = [line for line in stmt.splitlines()
             if not line.lstrip().startswith("--")]
    return "\n".join(lines).strip()


def _extract_db_name(url: str) -> str:
    """Extract database name from a SQLAlchemy URL."""
    # e.g. mysql+asyncmy://root:pass@localhost:3306/pptgenius → pptgenius
    m = re.search(r"/([^/?]+)(?:\?|$)", url)
    return m.group(1) if m else ""


async def create_tables():
    """Execute schema.sql — idempotent, skips pre-existing tables without warnings."""
    engine = _get_engine()
    settings = get_settings()
    db_name = _extract_db_name(settings.db.url)

    # --- 1. check database exists -------------------------------------------
    server_url = settings.db.url.rsplit("/", 1)[0] + "/mysql"
    server_engine = create_async_engine(server_url, echo=False)
    try:
        async with server_engine.begin() as conn:
            result = await conn.execute(
                text("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = :name"),
                {"name": db_name},
            )
            if result.fetchone() is None:
                _log.error("database '%s' does not exist — please create it first", db_name)
                return
    finally:
        await server_engine.dispose()

    # --- 2. discover existing tables ----------------------------------------
    async with engine.begin() as conn:
        result = await conn.execute(text("SHOW TABLES"))
        existing = {row[0] for row in result.fetchall()}

    # --- 3. execute schema, skip existing tables ----------------------------
    schema_path = RESOURCES_DIR / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")

    _create_table_re = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?", re.I)

    async with engine.begin() as conn:
        for statement in sql.split(";"):
            stmt = _strip_comments(statement)
            if not stmt:
                continue

            # Skip CREATE TABLE for tables that already exist
            m = _create_table_re.match(stmt)
            if m and m.group(1).lower() in existing:
                _log.debug("table '%s' already exists — skip", m.group(1))
                continue

            try:
                await conn.execute(text(stmt))
            except (OperationalError, ProgrammingError) as e:
                code = e.orig.args[0] if e.orig and e.orig.args else None  # type: ignore[union-attr]
                if code == _DUPLICATE_KEY:
                    _log.debug("index already exists — skip: %s", stmt[:50])
                else:
                    raise


async def init_db() -> None:
    """Full DB init: create tables then seed. Called once at startup."""
    await create_tables()
    from .seed import seed
    await seed(_get_engine())


_session_manager: "SessionManager | None" = None


def get_session_manager() -> "SessionManager":
    """Module-level singleton for sub-agents to get independent sessions."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


class SessionManager:
    """Provides independent DB sessions for parallel agent execution.

    Each call to ``new_session()`` returns a Database backed by a fresh
    AsyncSession from the connection pool.  Sessions are isolated —
    commits in one session do not affect others.  Callers must close
    each session via ``close()`` or ``async with``.
    """

    def __init__(self) -> None:
        self._sm = get_sessionmaker()

    def new_session(self) -> "Database":
        """Create a new independent Database + AsyncSession for an agent."""
        from .database import Database
        session = self._sm()
        return Database(session)

    async def close(self, db: "Database") -> None:
        """Close a session returned by new_session()."""
        try:
            await db.db.rollback()
        except Exception:
            pass
        try:
            await db.db.close()
        except Exception:
            pass


# Singleton — shared across the app
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


async def get_db() -> AsyncSession:
    sm = get_sessionmaker()
    async with sm() as session:
        yield session
