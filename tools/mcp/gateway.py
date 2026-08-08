"""
mcp.gateway - MCP Gateway: unified auth, routing, audit for all MCP calls

Author: le
Date: 2026/7/30
Version: 0.3
Task: Implement MCP Gateway with routing, JWT auth, RBAC, and audit logging
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from tools.logger import get_logger, log_mcp_call

logger = get_logger(__name__)


# ============================================================
# JWT 认证依赖（Gateway 内联，避免循环导入 backend.middleware）
# ============================================================


async def _verify_gateway_token(request: Request) -> dict:
    """
    验证 MCP Gateway 请求的 JWT Bearer Token。

    通过配置中的 JWT secret 校验 Token，返回 payload。
    不做 DB 查询，仅做 JWT 签名校验 + 基本字段提取。

    Returns:
        {"user_id": str, "role": str, "tenant_id": str}

    Raises:
        HTTPException 401: Token 缺失或无效
    """
    from jose import JWTError, jwt

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MCP Gateway 需要认证 (Authorization: Bearer <token>)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:]
    try:
        from backend.config import get_settings
        settings = get_settings()
        payload = jwt.decode(
            token, settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 JWT Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 缺少用户标识",
        )

    return {
        "user_id": user_id,
        "role": payload.get("role", "user"),
        "tenant_id": payload.get("tenant_id", "default"),
    }


def _require_role(*allowed_roles: str):
    """
    RBAC 依赖工厂：要求用户拥有指定角色之一。

    用法:
        @router.post("/tools/call")
        async def call_tool(request, user=Depends(_require_role("admin", "agent"))):
    """

    async def _check(user: dict = Depends(_verify_gateway_token)) -> dict:
        if user["role"] not in allowed_roles:
            logger.warning(
                "MCP Gateway RBAC 拒绝: user={} role={} required={}",
                user["user_id"], user["role"], allowed_roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"角色 {user['role']} 无权调用 MCP 工具 (需要 {', '.join(allowed_roles)})",
            )
        return user

    return _check


# ============================================================
# Gateway 请求模型
# ============================================================


class ListToolsRequest(BaseModel):
    server_name: str = Field(description="目标 Server 名称")


class CallToolRequest(BaseModel):
    server_name: str = Field(description="目标 Server 名称")
    tool_name: str = Field(description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="调用参数")


class CallToolResponse(BaseModel):
    success: bool = True
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    server_name: str = ""
    tool_name: str = ""


# ============================================================
# MCPGateway
# ============================================================


class MCPGateway:
    """
    MCP Gateway — 统一网关。

    职责：
    1. 路由：根据 tool_name → server_name 映射转发请求
    2. 审计：通过 log_mcp_call 记录所有调用
    3. 健康聚合：返回所有 Server 的健康状态

    Phase 3 新增：RBAC 权限、限流、Token 认证

    使用方式:
        gateway = MCPGateway()
        app = gateway.build_app()
        uvicorn.run(app, port=12001)
    """

    SERVER_URLS: dict[str, str] = {
        "policy_server": "http://localhost:12011",
        "material_server": "http://localhost:12021",
        "workflow_server": "http://localhost:12031",
    }

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── App 构建 ──

    def build_app(self) -> FastAPI:
        """构建 FastAPI Gateway 应用"""
        app = FastAPI(
            title="MCP Gateway",
            version="0.2.0",
            description="MCP 统一网关 — 路由、审计、服务发现",
        )

        # 根路径健康检查（供容器 healthcheck 使用，避免依赖各 Server 状态）
        @app.get("/health")
        async def root_health():
            """简单健康检查 — 仅确认 Gateway 进程存活"""
            return {"status": "healthy", "gateway": "MCP Gateway v0.2.0"}

        router = APIRouter(prefix="/api")

        @router.post("/tools/list")
        async def list_tools(
            request: ListToolsRequest,
            user: dict = Depends(_verify_gateway_token),
        ):
            """聚合所有或指定 Server 的工具列表"""
            server_name = request.server_name
            url = self.SERVER_URLS.get(server_name)
            if not url:
                raise HTTPException(400, f"Unknown server: {server_name}")

            client = await self._ensure_client()
            try:
                resp = await client.post(f"{url}/tools/list", json={})
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as e:
                logger.error("Gateway: failed to list tools from {}: {}", server_name, e)
                raise HTTPException(502, f"Server {server_name} unreachable")

        @router.post("/tools/call")
        async def call_tool(
            request: CallToolRequest,
            user: dict = Depends(_require_role("admin", "agent")),
        ):
            """转发工具调用到对应 MCP Server（需 admin/agent 角色）"""
            server_name = request.server_name
            tool_name = request.tool_name
            url = self.SERVER_URLS.get(server_name)
            if not url:
                raise HTTPException(400, f"Unknown server: {server_name}")

            start = time.perf_counter()

            client = await self._ensure_client()
            try:
                resp = await client.post(
                    f"{url}/tools/call",
                    json={
                        "server_name": server_name,
                        "tool_name": tool_name,
                        "arguments": request.arguments,
                    },
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
                resp.raise_for_status()
                data = resp.json()

                # 审计日志
                log_mcp_call(
                    server_name, tool_name,
                    request.arguments,
                    data.get("result"),
                    elapsed_ms,
                    "success" if data.get("success") else "failed",
                )

                return CallToolResponse(
                    success=data.get("success", True),
                    result=data.get("result"),
                    error=data.get("error"),
                    server_name=server_name,
                    tool_name=tool_name,
                )

            except httpx.HTTPError as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                log_mcp_call(
                    server_name, tool_name,
                    request.arguments, None,
                    elapsed_ms, "failed", str(e),
                )
                raise HTTPException(502, f"Server {server_name} unreachable: {e}")

        @router.get("/health")
        async def gateway_health():
            """Gateway 健康检查 + 各 Server 健康状态聚合"""
            servers_status = {}
            client = await self._ensure_client()
            for name, url in self.SERVER_URLS.items():
                try:
                    resp = await client.get(f"{url}/health", timeout=5.0)
                    servers_status[name] = "healthy" if resp.status_code == 200 else "unhealthy"
                except Exception as e:
                    servers_status[name] = "unreachable"
                    logger.warning("MCP Server {} ({}) 不可达: {}", name, url, e)

            all_healthy = all(v == "healthy" for v in servers_status.values())
            return {
                "status": "healthy" if all_healthy else "degraded",
                "gateway": "MCP Gateway v0.2.0",
                "servers": servers_status,
            }

        app.include_router(router)
        return app


# ============================================================
# 模块级 app 实例（uvicorn 入口）
# ============================================================

gateway = MCPGateway()
app = gateway.build_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=12001, log_level="info")
