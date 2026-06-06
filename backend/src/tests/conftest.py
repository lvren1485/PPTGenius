import os
import sys

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pptgenius.infrastructure.config.settings import get_settings
from pptgenius.infrastructure.db.models import Base

_prod_url = get_settings().db.url
_test_url = _prod_url.rsplit("/", 1)[0] + "/pptgenius_test"


@pytest_asyncio.fixture(scope="session")
async def engine():
    test_engine = create_async_engine(_test_url, echo=False, poolclass=NullPool)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    async with test_engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(list(Base.metadata.tables.values())):
            await conn.execute(text(f"DROP TABLE IF EXISTS `{table.name}`"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield session
