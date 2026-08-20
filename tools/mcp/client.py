"""
mcp.client - MCP Client: Agent-side tool discovery and invocation

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement MCP HTTP client for tool discovery and invocation through Gateway
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from tools.logger import get_logger, log_mcp_call

logger = get_logger(__name__)

# P2-5 无界治理：工具发现缓存 TTL（秒）与最大容量（超出淘汰最旧 Server）
_TOOL_CACHE_TTL = 300.0
_TOOL_CACHE_MAXSIZE = 64


def _record_tool_metric(tool_name: str, success: bool, latency_ms: float) -> None:
    """记录 MCP 工具调用指标（P2-2，agent 归属取自当前 trace 上下文，失败静默）。"""
    try:
        from governance.monitor import record_tool_call as _record
        from governance.trace import get_current_agent_name as _agent_name

        _record(
            tool_name=tool_name,
            agent_name=_agent_name(),
            success=success,
            latency_ms=latency_ms,
        )
    except Exception:
        pass


class MCPToolError(Exception):
    """MCP 工具调用返回错误"""


class MCPToolTimeout(Exception):
    """MCP 工具调用超时"""


class MCPClient:
    """
    MCP Client — Agent 侧工具发现和调用入口。

    架构: Agent → MCPClient → MCP Gateway → MCP Server → Business Logic

    使用方式:
        client = MCPClient(gateway_url="http://localhost:12001")
        tools = await client.list_tools("policy_server")
        result = await client.call_tool("policy_server", "search_policy", {"query": "..."})

    或通过 async context manager:
        async with MCPClient() as client:
            result = await client.call_tool(...)
    """

    def __init__(
        self,
        gateway_url: str = "http://localhost:12001",
        timeout: float = 30.0,
        auth_token: str = "",
    ):
        self._gateway_url = gateway_url.rstrip("/")
        self._timeout = timeout
        self._auth_token = auth_token  # JWT Bearer Token for Gateway auth
        self._client: Optional[httpx.AsyncClient] = None
        # P2-5: 缓存值 (时间戳, 工具列表)，TTL 过期后重新拉取，容量超限淘汰最旧
        self._tool_cache: dict[str, tuple[float, list[dict]]] = {}

    def _auth_headers(
        self,
        trace_id: str = "",
        user_context: Optional[dict] = None,
    ) -> dict[str, str]:
        """构建认证请求头（Bearer Token + 可选 trace_id 透传）。

        user_context 提供 {user_id, role, tenant_id} 时，以当前用户身份签发
        Gateway 调用 Token，保证办件/审计中的用户身份与请求用户一致。
        """
        token = self._auth_token
        if user_context:
            try:
                from backend.middleware.auth import create_access_token
                token = create_access_token(
                    user_id=user_context.get("user_id", "unknown"),
                    role=user_context.get("role", "user"),
                    tenant_id=user_context.get("tenant_id", "default"),
                )
            except Exception as e:
                logger.warning("按用户上下文签发 MCP Token 失败，回退默认 Token: {}", e)

        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if trace_id:
            headers["X-Trace-Id"] = trace_id
        return headers

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """惰性创建 httpx 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    # ── 工具发现 ──

    async def list_tools(self, server_name: str, trace_id: str = "") -> list[dict]:
        """
        发现指定 Server 上的所有工具。

        Args:
            server_name: "policy_server" | "material_server" | "workflow_server"
            trace_id: 链路追踪 ID（透传给 Gateway 用于审计关联）

        Returns:
            工具定义列表 [{name, description, input_schema, output_schema}]

        Raises:
            MCPToolError: Gateway 不可用或返回错误时快速失败
        """
        cached = self._tool_cache.get(server_name)
        if cached is not None:
            ts, tools = cached
            if time.time() - ts < _TOOL_CACHE_TTL:
                return tools
            # 缓存过期，移除后重新拉取
            self._tool_cache.pop(server_name, None)

        client = await self._ensure_client()
        try:
            resp = await client.post(
                f"{self._gateway_url}/api/tools/list",
                json={"server_name": server_name},
                headers=self._auth_headers(trace_id=trace_id),
            )
            resp.raise_for_status()
            data = resp.json()
            tools = data.get("tools", [])
            self._tool_cache[server_name] = (time.time(), tools)
            # 容量治理：超出上限时淘汰最早插入的 Server 缓存
            if len(self._tool_cache) > _TOOL_CACHE_MAXSIZE:
                self._tool_cache.pop(next(iter(self._tool_cache)), None)
            return tools
        except Exception as e:
            logger.error("MCP Gateway 工具发现失败（不再直连 Server）: {} {}", server_name, e)
            raise MCPToolError(
                f"{server_name} 工具发现失败，MCP Gateway 不可用或返回错误: {e}"
            ) from e

    # ── 工具调用 ──

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        trace_id: str = "",
        user_context: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        调用指定工具。

        Args:
            server_name: Server 名称
            tool_name: 工具名称
            arguments: 调用参数
            trace_id: 链路追踪 ID（透传给 Gateway 用于审计关联）
            user_context: 当前用户身份 {user_id, role, tenant_id}，用于按用户签发 Token

        Returns:
            工具返回结果 dict

        Raises:
            MCPToolError: 工具调用失败
            MCPToolTimeout: 调用超时
        """
        start = time.perf_counter()

        try:
            result = await self._call_via_gateway(
                server_name, tool_name, arguments,
                trace_id=trace_id,
                user_context=user_context,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            log_mcp_call(server_name, tool_name, arguments, result, elapsed_ms, "success")
            _record_tool_metric(tool_name, success=True, latency_ms=elapsed_ms)
            return result

        except (MCPToolError, MCPToolTimeout):
            raise

        except httpx.TimeoutException:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log_mcp_call(server_name, tool_name, arguments, None, elapsed_ms, "timeout")
            _record_tool_metric(tool_name, success=False, latency_ms=elapsed_ms)
            raise MCPToolTimeout(f"{server_name}/{tool_name}: timeout after {self._timeout}s")

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log_mcp_call(server_name, tool_name, arguments, None, elapsed_ms, "failed", str(e))
            _record_tool_metric(tool_name, success=False, latency_ms=elapsed_ms)
            raise MCPToolError(f"{server_name}/{tool_name}: {e}") from e

    async def _call_via_gateway(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict,
        trace_id: str = "",
        user_context: Optional[dict] = None,
    ) -> dict:
        """通过 Gateway 转发调用"""
        client = await self._ensure_client()
        resp = await client.post(
            f"{self._gateway_url}/api/tools/call",
            json={
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
            },
            headers=self._auth_headers(trace_id=trace_id, user_context=user_context),
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise MCPToolError(
                f"Gateway 拒绝调用 {server_name}/{tool_name}: HTTP {resp.status_code} {detail}"
            )
        data = resp.json()

        if not data.get("success", True):
            raise MCPToolError(data.get("error", "Unknown error"))

        return data.get("result", {})

    def clear_cache(self) -> None:
        """清除工具缓存"""
        self._tool_cache.clear()
