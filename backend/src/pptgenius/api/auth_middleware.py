"""Auth middleware — intercepts /api/*, validates Bearer token, sets request.state.user_id.

Public paths (no auth required):
  - POST /api/auth/register
  - POST /api/auth/login
  - GET  /api/health
  - GET  /api/config
  - OPTIONS (CORS preflight)
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from pptgenius.infrastructure.auth import decode_token

_PUBLIC_PATHS: set[tuple[str, str]] = {
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("GET",  "/api/health"),
    ("GET",  "/api/config"),
}


def _strip_query(path: str) -> str:
    return path.split("?")[0]


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only intercept /api/*
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        # CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Public paths
        key = (request.method, _strip_query(request.url.path))
        if key in _PUBLIC_PATHS:
            return await call_next(request)

        # Validate token
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                {"code": 40100, "message": "缺少认证令牌"},
                status_code=401,
            )

        token = auth[7:]
        payload = decode_token(token)
        if payload is None:
            return JSONResponse(
                {"code": 40100, "message": "令牌无效或已过期"},
                status_code=401,
            )

        request.state.user_id = payload["user_id"]
        return await call_next(request)
