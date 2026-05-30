"""Auth endpoints — register, login."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pptgenius.infrastructure.auth import create_token, hash_password, verify_password
from pptgenius.infrastructure.db import Database

from .deps import get_db
from .schemas import ApiResponse, AuthTokenData, LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(
    req: RegisterRequest,
    db: Database = Depends(get_db),
) -> ApiResponse[AuthTokenData]:
    existing = await db.get_user_by_name(req.name)
    if existing is not None:
        raise HTTPException(409, {"code": 40101, "message": "用户名已存在"})

    user = await db.create_user(name=req.name, password=hash_password(req.password))
    token = create_token(user.id)
    return ApiResponse(data=AuthTokenData(token=token, user_id=user.id, name=user.name))


@router.post("/login")
async def login(
    req: LoginRequest,
    db: Database = Depends(get_db),
) -> ApiResponse[AuthTokenData]:
    user = await db.get_user_by_name(req.name)
    if user is None or not verify_password(req.password, user.password):
        raise HTTPException(401, {"code": 40102, "message": "用户名或密码错误"})

    token = create_token(user.id)
    return ApiResponse(data=AuthTokenData(token=token, user_id=user.id, name=user.name))
