"""PPTGenius FastAPI 应用定义."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pptgenius.infrastructure.utils import get_logger, setup_logging_from_config

_log = get_logger(__name__)


# -- lifespan ----------------------------------------------------------------

async def _init_db() -> None:
    """Ensure database tables exist + seed initial data (non-destructive)."""
    from pptgenius.infrastructure.db import init_db

    await init_db()
    _log.info("database tables ensured + seeded")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging_from_config()
    _log.info("PPTGenius %s starting", app.version)
    await _init_db()
    _log.info("startup complete")
    yield
    _log.info("PPTGenius shutting down")
    from pptgenius.infrastructure.db import dispose_engine
    await dispose_engine()


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

    # Auth middleware (after CORS so preflight passes)
    from pptgenius.api.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)

    # Register API routes
    from pptgenius.api.router import api_router
    app.include_router(api_router)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    config = uvicorn.Config(
        "pptgenius.main:app", host="0.0.0.0", port=8000, reload=True,
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        server.should_exit = True


if __name__ == "__main__":
    main()
