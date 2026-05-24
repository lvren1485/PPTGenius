"""PPTGenius FastAPI 应用定义."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pptgenius.infrastructure.utils.logger import get_logger, setup_logging_from_config

_log = get_logger(__name__)


# -- lifespan ----------------------------------------------------------------

async def _init_db() -> None:
    """Ensure database tables exist (non-destructive)."""
    from pptgenius.infrastructure.db.engine import create_tables

    await create_tables()
    _log.info("database tables ensured")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging_from_config()
    _log.info("PPTGenius %s starting", app.version)
    await _init_db()
    _log.info("startup complete")
    yield
    _log.info("PPTGenius shutting down")


# -- app ---------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="PPTGenius",
        version="0.1.0",
        description="单人 AI PPT 生成网站",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    from pptgenius.api.router import api_router
    app.include_router(api_router)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("pptgenius.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
