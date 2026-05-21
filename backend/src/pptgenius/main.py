"""PPTGenius FastAPI 应用定义."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    app = FastAPI(
        title="PPTGenius",
        version="0.1.0",
        description="单人 AI PPT 生成网站",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        return {"code": 0, "message": "ok", "data": {"status": "healthy"}}

    # 注册路由 (待实现)
    # from pptgenius.api.router import register_routers
    # register_routers(app)

    return app


app = create_app()


def main():
    import uvicorn

    uvicorn.run("pptgenius.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
