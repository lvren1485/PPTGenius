"""DB — SQLAlchemy async engine, ORM models, and the Database thin wrapper.

Usage::

    from pptgenius.infrastructure.db import Database, init_db

    await init_db()  # creates tables + seeds
    db = Database(async_session)
    user = await db.create_user("alice")
"""

from .database import Database
from .engine import create_tables, get_db, get_session_manager, init_db

__all__ = [
    "Database",
    "create_tables",
    "get_db",
    "get_session_manager",
    "init_db",
]
