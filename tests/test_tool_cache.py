"""
test_tool_cache - P2-5 MCP 工具发现缓存 TTL 与容量治理测试

验证：
1. 缓存命中时不再请求 Gateway；
2. TTL 过期后重新拉取；
3. 容量超限时淘汰最早插入的缓存，内存有界。
"""
from __future__ import annotations

import pytest

from tools.mcp.client import MCPClient, _TOOL_CACHE_MAXSIZE, _TOOL_CACHE_TTL


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeHTTPX:
    def __init__(self):
        self.calls = 0

    async def post(self, url, json=None, headers=None):
        self.calls += 1
        return _FakeResponse({"tools": [{"name": f"tool_{self.calls}"}]})


@pytest.mark.asyncio
async def test_cache_hit_avoids_gateway_request():
    client = MCPClient(gateway_url="http://test:12001")
    fake = _FakeHTTPX()
    client._client = fake

    tools1 = await client.list_tools("policy_server")
    tools2 = await client.list_tools("policy_server")

    assert tools1 == tools2 == [{"name": "tool_1"}]
    assert fake.calls == 1  # 第二次命中缓存，未请求 Gateway


@pytest.mark.asyncio
async def test_cache_expires_after_ttl():
    client = MCPClient(gateway_url="http://test:12001")
    fake = _FakeHTTPX()
    client._client = fake

    await client.list_tools("policy_server")
    assert fake.calls == 1

    # 把缓存时间戳改到 TTL 之前，触发重新拉取
    ts, tools = client._tool_cache["policy_server"]
    client._tool_cache["policy_server"] = (ts - _TOOL_CACHE_TTL - 1, tools)

    await client.list_tools("policy_server")
    assert fake.calls == 2


@pytest.mark.asyncio
async def test_cache_maxsize_evicts_oldest():
    client = MCPClient(gateway_url="http://test:12001")
    fake = _FakeHTTPX()
    client._client = fake

    total = _TOOL_CACHE_MAXSIZE + 5
    for i in range(total):
        await client.list_tools(f"server_{i}")

    assert len(client._tool_cache) <= _TOOL_CACHE_MAXSIZE
    # 最早插入的 5 个 Server 已被淘汰
    assert "server_0" not in client._tool_cache
    assert f"server_{total - 1}" in client._tool_cache
