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


class MCPToolError(Exception):
    """MCP 工具调用返回错误"""


class MCPToolTimeout(Exception):
    """MCP 工具调用超时"""


class MCPClient:
    """
    MCP Client — Agent 侧工具发现和调用入口。

    架构: Agent → MCPClient → MCP Gateway → MCP Server → Business Logic

    使用方式:
        client = MCPClient(gateway_url="http://localhost:12300")
        tools = await client.list_tools("policy_server")
        result = await client.call_tool("policy_server", "search_policy", {"query": "..."})

    或通过 async context manager:
        async with MCPClient() as client:
            result = await client.call_tool(...)
    """

    # ── Server → Gateway 端口映射 ──
    # 当 Gateway 不可用时，Client 可以直连 Server（fallback）
    SERVER_PORTS: dict[str, int] = {
        "policy_server": 12301,
        "material_server": 12302,
        "workflow_server": 12303,
    }

    def __init__(
        self,
        gateway_url: str = "http://localhost:12300",
        timeout: float = 30.0,
        auth_token: str = "",
    ):
        self._gateway_url = gateway_url.rstrip("/")
        self._timeout = timeout
        self._auth_token = auth_token  # JWT Bearer Token for Gateway auth
        self._client: Optional[httpx.AsyncClient] = None
        self._tool_cache: dict[str, list[dict]] = {}

    def _auth_headers(self) -> dict[str, str]:
        """构建认证请求头"""
        if self._auth_token:
            return {"Authorization": f"Bearer {self._auth_token}"}
        return {}

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

    async def list_tools(self, server_name: str) -> list[dict]:
        """
        发现指定 Server 上的所有工具。

        Args:
            server_name: "policy_server" | "material_server" | "workflow_server"

        Returns:
            工具定义列表 [{name, description, input_schema, output_schema}]
        """
        if server_name in self._tool_cache:
            return self._tool_cache[server_name]

        client = await self._ensure_client()
        try:
            resp = await client.post(
                f"{self._gateway_url}/api/tools/list",
                json={"server_name": server_name},
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            tools = data.get("tools", [])
            self._tool_cache[server_name] = tools
            return tools
        except httpx.HTTPError:
            # Gateway 不可用 → 尝试直连 Server
            return await self._list_tools_direct(server_name)

    async def _list_tools_direct(self, server_name: str) -> list[dict]:
        """直连 MCP Server 获取工具列表（Gateway fallback）"""
        port = self.SERVER_PORTS.get(server_name)
        if not port:
            return []

        client = await self._ensure_client()
        try:
            resp = await client.post(
                f"http://localhost:{port}/tools/list",
                json={},
            )
            resp.raise_for_status()
            data = resp.json()
            tools = data.get("tools", [])
            self._tool_cache[server_name] = tools
            return tools
        except Exception as e:
            logger.warning("Failed to list tools from {}: {}", server_name, e)
            return []

    # ── 工具调用 ──

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        调用指定工具。

        Args:
            server_name: Server 名称
            tool_name: 工具名称
            arguments: 调用参数

        Returns:
            工具返回结果 dict

        Raises:
            MCPToolError: 工具调用失败
            MCPToolTimeout: 调用超时
        """
        start = time.perf_counter()

        try:
            result = await self._call_via_gateway(server_name, tool_name, arguments)
            elapsed_ms = (time.perf_counter() - start) * 1000
            log_mcp_call(server_name, tool_name, arguments, result, elapsed_ms, "success")
            return result

        except (MCPToolError, MCPToolTimeout):
            raise

        except httpx.TimeoutException:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log_mcp_call(server_name, tool_name, arguments, None, elapsed_ms, "timeout")
            raise MCPToolTimeout(f"{server_name}/{tool_name}: timeout after {self._timeout}s")

        except Exception as e:
            # Gateway 失败 → 尝试直连 Server
            logger.info("Gateway call failed, trying direct connection: {}", e)
            try:
                result = await self._call_direct(server_name, tool_name, arguments)
                elapsed_ms = (time.perf_counter() - start) * 1000
                log_mcp_call(server_name, tool_name, arguments, result, elapsed_ms, "success")
                return result
            except Exception as e2:
                elapsed_ms = (time.perf_counter() - start) * 1000
                log_mcp_call(server_name, tool_name, arguments, None, elapsed_ms, "failed", str(e2))
                raise MCPToolError(f"{server_name}/{tool_name}: {e2}")

    async def _call_via_gateway(
        self, server_name: str, tool_name: str, arguments: dict
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
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success", True):
            raise MCPToolError(data.get("error", "Unknown error"))

        return data.get("result", {})

    async def _call_direct(
        self, server_name: str, tool_name: str, arguments: dict
    ) -> dict:
        """直连 MCP Server（Gateway fallback）"""
        port = self.SERVER_PORTS.get(server_name)
        if not port:
            raise MCPToolError(f"Unknown server: {server_name}")

        client = await self._ensure_client()
        resp = await client.post(
            f"http://localhost:{port}/tools/call",
            json={
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success", True):
            raise MCPToolError(data.get("error", "Unknown error"))

        return data.get("result", {})

    def clear_cache(self) -> None:
        """清除工具缓存"""
        self._tool_cache.clear()
