"""
backend.middleware.auth - JWT authentication middleware: token validation, user identity extraction

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement JWT-based authentication middleware
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import get_settings

# ============================================================
# Bearer Token 方案
# ============================================================

bearer_scheme = HTTPBearer(
    auto_error=False,  # 不自动报 401，允许无认证的公开端点
    description="JWT Bearer Token (Authorization: Bearer <token>)",
)


# ============================================================
# 依赖注入
# ============================================================


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = None,
) -> dict:
    """
    FastAPI 依赖：验证 JWT Token，返回当前用户信息。

    用法:
        @app.get("/protected")
        async def endpoint(user: dict = Depends(get_current_user)): ...

    Args:
        credentials: Bearer Token（FastAPI 自动从 Header 解析）

    Returns:
        {"user_id": str, "role": str, "tenant_id": str}

    Raises:
        HTTPException 401: Token 无效或缺失
    """
    settings = get_settings()

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请提供认证凭证 (Authorization: Bearer <token>)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise credentials_exception

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise credentials_exception

    return {
        "user_id": user_id,
        "role": payload.get("role", "user"),
        "tenant_id": payload.get("tenant_id", "default"),
    }


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = None,
) -> Optional[dict]:
    """
    FastAPI 依赖：可选鉴权。有 Token 则解析，无则返回 None。

    用于既允许匿名访问又想获取用户信息的端点。
    """
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# ============================================================
# 中间件 — 请求级鉴权（兼容 X-User-Id Header）
# ============================================================


class AuthMiddleware(BaseHTTPMiddleware):
    """
    FastAPI 认证中间件。

    优先级:
      1. Authorization: Bearer <token> — JWT 认证
      2. X-User-Id Header — 简化模式（开发/内部调用）
      3. 无认证信息 — 401

    使用方式:
        app.add_middleware(AuthMiddleware)
    """

    def __init__(self, app=None, **kwargs):
        super().__init__(app, **kwargs)

    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查和文档端点
        if request.url.path in ("/health", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        # 优先 JWT Bearer Token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            settings = get_settings()
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token, settings.jwt_secret_key,
                    algorithms=[settings.jwt_algorithm],
                )
                request.state.user_id = payload.get("sub", "unknown")
                request.state.user_role = payload.get("role", "user")
                request.state.user_tenant = payload.get("tenant_id", "default")
                return await call_next(request)
            except JWTError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的 JWT Token",
                )

        # 无认证
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请提供认证信息 (Authorization: Bearer <token>)",
        )


# ============================================================
# Token 生成工具
# ============================================================


def create_access_token(
    user_id: str,
    role: str = "user",
    tenant_id: str = "default",
) -> str:
    """
    生成 JWT Token。

    Args:
        user_id: 用户ID
        role: 角色 (admin / agent / user)
        tenant_id: 租户ID

    Returns:
        JWT Token 字符串
    """
    from datetime import datetime, timedelta, timezone

    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)

    payload = {
        "sub": user_id,
        "role": role,
        "tenant_id": tenant_id,
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
