"""
A2A Connector HTTP 握手单元测试（DB-free）。

用 httpx.MockTransport 模拟外部 Agent 的 POST /tasks 响应，覆盖:
    - 同步完成（completed）→ connector 直接返回 artifact，不挂起
    - 异步提交（submitted）→ 返回 mode=http 等回调
    - 异步失败（failed）→ 反映失败状态
    - 默认 callback_url 透传到请求体
    - endpoint 不可达 → stub fallback
"""
from __future__ import annotations

import json

import httpx
import pytest

from orchestration.langgraph.state import A2ATaskStatus
from tools.a2a.connector import A2AConnector
from tools.a2a.protocol import AgentCard, AgentHealth
from tools.a2a.registry import ExternalAgentRegistry
from tools.a2a.task import TaskStore


def _make_registry(endpoint: str = "http://mock-housing") -> ExternalAgentRegistry:
    reg = ExternalAgentRegistry()
    reg.register(AgentCard(
        name="housing_agent",
        display_name="不动产系统Agent",
        description="提供不动产登记查询等服务",
        skills=["query_property"],
        endpoint=endpoint,
        version="0.1.0",
        timeout_ms=15000,
    ))
    reg.set_health("housing_agent", AgentHealth.HEALTHY)
    return reg


def _make_connector(
    handler,
    endpoint: str = "http://mock-housing",
    default_callback_url: str = "",
) -> tuple[A2AConnector, TaskStore]:
    store = TaskStore()
    conn = A2AConnector(
        registry=_make_registry(endpoint),
        task_store=store,
        default_callback_url=default_callback_url,
    )
    # 注入带 MockTransport 的 HTTP 客户端
    conn._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(5.0),
    )
    return conn, store


def _req_body(request: httpx.Request) -> dict:
    """读取 httpx.Request 的 JSON body。"""
    return json.loads(request.content)


@pytest.mark.asyncio
async def test_send_task_sync_completed():
    """外部 Agent 同步返回 completed → connector 直接返回结果并落库为 completed。"""

    def handler(request: httpx.Request) -> httpx.Response:
        body = _req_body(request)
        assert body["callback_url"] == ""  # 未配置默认回调
        return httpx.Response(200, json={
            "task_id": body["task_id"],
            "status": "completed",
            "artifact": {"total_count": 2, "properties": []},
            "agent_name": "housing_agent",
        })

    conn, store = _make_connector(handler)
    try:
        result = await conn.send_task(
            "query_property", {"owner_name": "张三"}, source_trace_id="trace_001",
        )
        assert result["mode"] == "http"
        assert result["status"] == "completed"
        assert result["artifact"]["total_count"] == 2

        record = store.get(result["task_id"])
        assert record is not None
        assert record.status == A2ATaskStatus.COMPLETED
        assert record.source_trace_id == "trace_001"  # 回调后恢复 checkpoint 的依据
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_task_async_submitted():
    """外部 Agent 返回 submitted → connector 标记为异步等待回调。"""

    def handler(request: httpx.Request) -> httpx.Response:
        body = _req_body(request)
        return httpx.Response(200, json={
            "task_id": body["task_id"],
            "status": "submitted",
            "agent_name": "housing_agent",
            "artifact": None,
        })

    conn, store = _make_connector(handler)
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        assert result["mode"] == "http"
        assert result["status"] == "submitted"
        assert result["artifact"] is None

        record = store.get(result["task_id"])
        assert record is not None
        assert record.status == A2ATaskStatus.SUBMITTED  # 等待回调推进
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_task_async_failed():
    """外部 Agent 返回 failed → connector 反映失败状态。"""

    def handler(request: httpx.Request) -> httpx.Response:
        body = _req_body(request)
        return httpx.Response(200, json={
            "task_id": body["task_id"],
            "status": "failed",
            "error_message": "外部系统繁忙",
            "agent_name": "housing_agent",
        })

    conn, store = _make_connector(handler)
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        assert result["mode"] == "http"
        assert result["status"] == "failed"
        record = store.get(result["task_id"])
        assert record is not None
        assert record.status == A2ATaskStatus.FAILED
        assert record.error_message == "外部系统繁忙"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_task_default_callback_url_propagated():
    """Connector 的 default_callback_url 应透传到外部 Agent 请求体。"""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = _req_body(request)
        seen["callback_url"] = body.get("callback_url")
        return httpx.Response(200, json={
            "task_id": body["task_id"],
            "status": "submitted",
            "agent_name": "housing_agent",
        })

    conn, _ = _make_connector(
        handler, default_callback_url="http://api:12401/api/a2a/callback",
    )
    try:
        await conn.send_task("query_property", {"owner_name": "张三"})
        assert seen["callback_url"] == "http://api:12401/api/a2a/callback"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_task_stub_fallback_when_unreachable():
    """外部 Agent 不可达（真实连接失败）+ 显式开发开关 → 回退 stub，任务仍完成且带 artifact。"""
    store = TaskStore()
    conn = A2AConnector(
        registry=_make_registry(endpoint="http://127.0.0.1:9"),  # 未监听端口
        task_store=store,
        allow_stub=True,  # 显式开发开关
    )
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        assert result["mode"] == "stub"
        assert result["status"] == "completed"
        assert result["artifact"] is not None
        # stub fallback 原因应记录（可追踪，非静默）
        assert result.get("error_message")
        record = store.get(result["task_id"])
        assert record is not None
        assert record.status == A2ATaskStatus.COMPLETED
        assert record.error_message  # fallback 原因写入记录
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_task_no_stub_fails_when_unreachable():
    """生产默认（allow_stub=False）外部 Agent 不可达 → 明确失败，禁止 stub 假结果。"""
    store = TaskStore()
    conn = A2AConnector(
        registry=_make_registry(endpoint="http://127.0.0.1:9"),  # 未监听端口
        task_store=store,
        allow_stub=False,
    )
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        assert result["mode"] == "http"
        assert result["status"] == "failed"
        assert result["artifact"] is None
        assert result.get("error_message"), "失败原因必须可追踪"
        record = store.get(result["task_id"])
        assert record is not None
        assert record.status == A2ATaskStatus.FAILED
        assert "外部 Agent" in record.error_message
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_task_unknown_skill_uses_stub():
    """无注册 Agent 的技能 + 显式开发开关 → 直接 stub。"""
    reg = ExternalAgentRegistry()  # 空注册中心，无 housing_agent
    store = TaskStore()
    conn = A2AConnector(registry=reg, task_store=store, allow_stub=True)
    try:
        result = await conn.send_task("unknown_skill", {"data": "x"})
        assert result["mode"] == "stub"
        assert result["task_id"].startswith("a2a_")
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_task_unknown_skill_no_stub_fails():
    """无注册 Agent 的技能 + 生产禁止 stub → 明确失败。"""
    reg = ExternalAgentRegistry()  # 空注册中心
    store = TaskStore()
    conn = A2AConnector(registry=reg, task_store=store, allow_stub=False)
    try:
        result = await conn.send_task("unknown_skill", {"data": "x"})
        assert result["status"] == "failed"
        assert result["artifact"] is None
        assert "未注册" in result["error_message"]
        record = store.get(result["task_id"])
        assert record.status == A2ATaskStatus.FAILED
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_check_status_after_stub_send():
    """stub 完成后 check_status 返回 completed + artifact。"""
    # 用真实 httpx 客户端（不注入 MockTransport），127.0.0.1:9 不可达 → stub
    store = TaskStore()
    conn = A2AConnector(
        registry=_make_registry(endpoint="http://127.0.0.1:9"),
        task_store=store,
        allow_stub=True,
    )
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        assert result["mode"] == "stub"
        status = await conn.check_status(result["task_id"])
        assert status["status"] == "completed"
        assert status["artifact"] is not None
        assert status["task_id"] == result["task_id"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_check_status_unknown_task():
    """不存在的任务 → status=unknown。"""
    conn, _ = _make_connector(handler=lambda req: httpx.Response(200, json={}))
    try:
        status = await conn.check_status("nonexistent_task")
        assert status["status"] == "unknown"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_cancel_task_submitted():
    """提交中的异步任务可取消。"""

    def handler(request: httpx.Request) -> httpx.Response:
        body = _req_body(request)
        return httpx.Response(200, json={
            "task_id": body["task_id"], "status": "submitted", "agent_name": "housing_agent",
        })

    conn, _ = _make_connector(handler)
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        cancel = await conn.cancel_task(result["task_id"])
        assert cancel["cancelled"] is True
        # 取消后状态为 failed（终态）
        status = await conn.check_status(result["task_id"])
        assert status["status"] == "failed"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_cancel_task_completed_not_allowed():
    """已完成（stub 终态）的任务不能取消。"""
    store = TaskStore()
    conn = A2AConnector(
        registry=_make_registry(endpoint="http://127.0.0.1:9"),  # 不可达 → stub 完成
        task_store=store,
        allow_stub=True,
    )
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        assert result["mode"] == "stub"
        cancel = await conn.cancel_task(result["task_id"])
        assert cancel["cancelled"] is False
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_cancel_task_not_found():
    """不存在的任务取消返回 False。"""
    conn, _ = _make_connector(handler=lambda req: httpx.Response(200, json={}))
    try:
        cancel = await conn.cancel_task("nonexistent_task")
        assert cancel["cancelled"] is False
    finally:
        await conn.close()


# ============================================================
# P1-6: 重试与可靠性
# ============================================================


@pytest.mark.asyncio
async def test_send_http_retries_on_5xx_then_succeeds():
    """5xx 触发重试，恢复后成功（外部系统瞬时故障可自愈）。"""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(500, json={"detail": "temporary failure"})
        body = _req_body(request)
        return httpx.Response(200, json={
            "task_id": body["task_id"],
            "status": "completed",
            "artifact": {"total_count": 1},
            "agent_name": "housing_agent",
        })

    conn, _ = _make_connector(handler)
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        assert result["mode"] == "http"
        assert result["status"] == "completed"
        assert len(calls) == 2, f"应重试 1 次，实际 {len(calls)} 次"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_http_4xx_does_not_retry():
    """4xx 客户端错误不重试，任务明确失败。"""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json={"detail": "bad request"})

    conn, _ = _make_connector(handler)
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        assert result["status"] == "failed"
        assert len(calls) == 1, f"4xx 不应重试，实际 {len(calls)} 次"
        assert "400" in result["error_message"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_http_all_retries_exhausted_fails():
    """重试用尽仍失败 → 任务 failed 且失败原因可追踪（禁止 stub 假结果）。"""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, json={"detail": "still down"})

    store = TaskStore()
    conn = A2AConnector(
        registry=_make_registry(endpoint="http://mock-housing"),
        task_store=store,
        allow_stub=False,   # 生产禁止 stub
        http_retries=2,     # 总尝试 3 次
        retry_backoff_base=0.0,  # 测试不等待
    )
    conn._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(5.0),
    )
    try:
        result = await conn.send_task("query_property", {"owner_name": "张三"})
        assert result["status"] == "failed"
        assert result["mode"] == "http"
        assert result["artifact"] is None
        assert result.get("error_message")
        assert len(calls) == 3, f"应重试 2 次共 3 次调用，实际 {len(calls)} 次"
        record = store.get(result["task_id"])
        assert record.status == A2ATaskStatus.FAILED
        assert "503" in record.error_message
    finally:
        await conn.close()
