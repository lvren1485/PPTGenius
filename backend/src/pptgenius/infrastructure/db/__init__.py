"""DB — SQLAlchemy async engine, ORM models, and the Database thin wrapper.

Usage::

    from pptgenius.infrastructure.db import Database, create_tables

    await create_tables()
    db = Database(async_session)
    user = await db.create_user("alice")
"""

from .database import Database
from .engine import create_tables, get_db

__all__ = [
    "Database",
    "create_tables",
    "get_db",
]
