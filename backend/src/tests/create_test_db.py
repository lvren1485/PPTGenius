import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    e = create_async_engine('mysql+asyncmy://root:root@localhost:3306/mysql')
    async with e.begin() as c:
        await c.execute(text('DROP DATABASE IF EXISTS pptgenius_test'))
        await c.execute(text('CREATE DATABASE pptgenius_test CHARACTER SET utf8mb4'))
    print('pptgenius_test database recreated')
    await e.dispose()

asyncio.run(main())
