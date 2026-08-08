"""
a2a.mock_agents.server - A2A Mock HTTP Server: expose external agents as HTTP services

Author: le
Date: 2026/8/2
Version: 0.1
Task: Expose housing_agent / fund_agent as FastAPI HTTP endpoints for real A2A over HTTP

端口约定:
    12101 — housing_agent（不动产系统）
    12111 — fund_agent（公积金系统）

与 tools.a2a.registry.initialize_default_agents() 中注册的 endpoint 一致。

Usage:
    python -m tools.a2a.mock_agents.server                # 启动全部
    python -m tools.a2a.mock_agents.server --housing-port 12101
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import os
import time
from typing import Any

from fastapi import FastAPI
import httpx

from tools.a2a.protocol import A2ATaskRequest, A2ATaskResponse, A2ATaskStatus
from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 异步回调 — 外部 Agent 完成后向 platform 回调
# ============================================================


def _status_value(status: A2ATaskStatus | str) -> str:
    """兼容 A2ATaskStatus 枚举与字符串的取值。"""
    return status.value if isinstance(status, A2ATaskStatus) else str(status)


def _build_callback_payload(response: A2ATaskResponse) -> dict[str, Any]:
    """
    构造与 backend/api/schemas.A2ACallbackRequest 一致的载荷。

    签名公式: hmac_sha256(A2A_HMAC_SECRET, f"{task_id}|{status}|{timestamp}")
    """
    secret = os.environ.get("A2A_HMAC_SECRET", "")
    timestamp = int(time.time())
    status = _status_value(response.status)
    sign_payload = f"{response.task_id}|{status}|{timestamp}"
    signature = (
        hmac.new(secret.encode("utf-8"), sign_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if secret
        else ""
    )
    return {
        "task_id": response.task_id,
        "status": status,
        "artifact": response.artifact,
        "error_message": response.error_message,
        "timestamp": timestamp,
        "signature": signature,
    }


async def _post_callback(callback_url: str, response: A2ATaskResponse) -> None:
    """向 platform 的 /api/a2a/callback 发送完成回调（失败重试 3 次，仅记日志）。"""
    payload = _build_callback_payload(response)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(3):
                try:
                    resp = await client.post(callback_url, json=payload)
                    resp.raise_for_status()
                    logger.info(
                        "A2A 回调成功: task={task_id} status={status} → {url}",
                        task_id=response.task_id,
                        status=payload["status"],
                        url=callback_url,
                    )
                    return
                except Exception as e:
                    logger.warning(
                        "A2A 回调失败 (attempt {}): {} — {error}",
                        attempt + 1, callback_url, error=e,
                    )
                    if attempt < 2:
                        await asyncio.sleep(0.5)
    except Exception as e:
        logger.error("A2A 回调客户端异常: {}", e)


async def _process_and_callback(agent: Any, request: A2ATaskRequest) -> None:
    """后台执行任务并回调结果（异步模式）。"""
    try:
        response = await agent.process_task(request)
    except Exception as e:
        logger.error("[{}] 任务执行异常: {}", getattr(agent, "agent_id", "agent"), e)
        response = A2ATaskResponse(
            task_id=request.task_id,
            status=A2ATaskStatus.FAILED,
            agent_name=getattr(agent, "agent_id", ""),
            error_message=str(e),
        )
    if request.callback_url:
        await _post_callback(request.callback_url, response)


# ============================================================
# Mock Server Factory
# ============================================================


def create_mock_server(agent, agent_name: str, port: int) -> FastAPI:
    """
    为单个外部 Agent 创建 FastAPI Mock Server。

    暴露端点:
        GET  /                    → AgentCard（能力描述）
        GET  /.well-known/agent   → AgentCard（A2A 标准发现端点）
        POST /tasks               → 接收 A2ATaskRequest，返回 A2ATaskResponse
        GET  /tasks/{task_id}     → 任务状态（mock 为同步完成）

    Args:
        agent: HousingAgent / FundAgent 实例
        agent_name: Agent 名称（仅用于日志）
        port: 监听端口（用于日志显示）

    Returns:
        FastAPI app
    """
    app = FastAPI(
        title=f"{agent_name} Mock Server",
        description="A2A 外部 Agent Mock 服务（本地开发用）",
        version="0.1.0",
    )

    @app.get("/")
    async def agent_card() -> dict[str, Any]:
        """返回 Agent 能力卡片"""
        return agent.card.model_dump()

    @app.get("/.well-known/agent")
    async def well_known() -> dict[str, Any]:
        """A2A 标准 Agent 发现端点"""
        return agent.card.model_dump()

    @app.post("/tasks", response_model=A2ATaskResponse)
    async def submit_task(request: A2ATaskRequest) -> A2ATaskResponse:
        """
        接收 A2A 任务。

        双模式:
            - 无 callback_url → 同步执行，直接返回结果（向后兼容）
            - 有 callback_url → 异步模式：立即返回 submitted，后台执行并回调结果
        """
        if request.callback_url:
            logger.info(
                "[{}] 异步模式 task={} skill={} → 将回调 {}",
                agent_name, request.task_id, request.skill, request.callback_url,
            )
            asyncio.create_task(_process_and_callback(agent, request))
            return A2ATaskResponse(
                task_id=request.task_id,
                status=A2ATaskStatus.SUBMITTED,
                agent_name=agent_name,
                artifact=None,
            )

        logger.info(
            "[{}] 同步模式 task={} skill={}",
            agent_name, request.task_id, request.skill,
        )
        return await agent.process_task(request)

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any]:
        """
        查询任务状态。

        Mock Agent 为同步执行，任务在 POST /tasks 时已返回结果。
        此端点用于演示 A2A 状态查询语义。
        """
        return {
            "task_id": task_id,
            "status": "completed",
            "agent_name": agent_name,
            "message": "Mock Agent 同步执行，任务结果在 POST /tasks 时已返回",
        }

    return app


# ============================================================
# 启动入口 — 同时启动 Housing + Fund 两个 Mock Server
# ============================================================


def build_apps(
    housing_port: int = 12101,
    fund_port: int = 12111,
) -> dict[str, FastAPI]:
    """
    构建 Housing + Fund 两个 Mock Server app。

    Args:
        housing_port: Housing Agent 端口
        fund_port: Fund Agent 端口

    Returns:
        {服务名: FastAPI app}
    """
    from tools.a2a.mock_agents.housing_agent import HousingAgent
    from tools.a2a.mock_agents.fund_agent import FundAgent

    housing_app = create_mock_server(
        HousingAgent(), "housing_agent", housing_port,
    )
    fund_app = create_mock_server(
        FundAgent(), "fund_agent", fund_port,
    )
    return {
        "housing": housing_app,
        "fund": fund_app,
    }


async def start_servers(
    housing_port: int = 12101,
    fund_port: int = 12111,
) -> None:
    """
    启动所有 Mock Server（一个进程内多个 uvicorn 实例）。

    Args:
        housing_port: Housing Agent 端口
        fund_port: Fund Agent 端口
    """
    import uvicorn

    apps = build_apps(housing_port, fund_port)

    async def _start(name: str, app: FastAPI, port: int) -> None:
        config = uvicorn.Config(
            app, host="0.0.0.0", port=port, log_level="info",
        )
        server = uvicorn.Server(config)
        print(f"[{name}] A2A Mock Server starting on port {port}...")
        await server.serve()

    print(f"Starting {len(apps)} A2A mock servers...")
    await asyncio.gather(
        _start("housing_agent", apps["housing"], housing_port),
        _start("fund_agent", apps["fund"], fund_port),
    )


def main() -> None:
    """CLI 入口"""
    parser = argparse.ArgumentParser(
        description="Start A2A Mock HTTP Servers (housing_agent + fund_agent)",
    )
    parser.add_argument("--housing-port", type=int, default=12101)
    parser.add_argument("--fund-port", type=int, default=12111)
    args = parser.parse_args()

    try:
        asyncio.run(start_servers(args.housing_port, args.fund_port))
    except KeyboardInterrupt:
        print("\nShutting down A2A mock servers...")


# ============================================================
# Smoke Test — python -m tools.a2a.mock_agents.server
# ============================================================

if __name__ == "__main__":
    import os
    import sys

    # 支持 --smoke 快速自检
    if "--smoke" in sys.argv:
        from fastapi.testclient import TestClient

        passed = 0
        failed = 0

        def check(name: str, condition: bool, detail: str = ""):
            global passed, failed
            if condition:
                passed += 1
                print(f"  [OK] {name}")
            else:
                failed += 1
                print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))

        print("=== A2A Mock Server smoke test ===")
        apps = build_apps()

        # ── Housing ──
        print("--- housing_agent ---")
        client = TestClient(apps["housing"])
        card = client.get("/.well-known/agent")
        check("well-known 200", card.status_code == 200)
        check("card name", card.json().get("name") == "housing_agent")
        check("skills", "query_property" in card.json().get("skills", []))

        task_resp = client.post("/tasks", json={
            "task_id": "a2a_smoke_001",
            "skill": "query_property",
            "input": {"owner_name": "张三"},
        })
        check("task 200", task_resp.status_code == 200)
        data = task_resp.json()
        check("task completed", data.get("status") == "completed")
        check("artifact properties", data.get("artifact", {}).get("total_count", 0) >= 1)

        # ── Fund ──
        print("--- fund_agent ---")
        client2 = TestClient(apps["fund"])
        card2 = client2.get("/")
        check("fund card 200", card2.status_code == 200)
        check("fund name", card2.json().get("name") == "fund_agent")

        task2 = client2.post("/tasks", json={
            "task_id": "a2a_smoke_002",
            "skill": "query_fund",
            "input": {"user_id": "001"},
        })
        check("fund task 200", task2.status_code == 200)
        data2 = task2.json()
        check("fund completed", data2.get("status") == "completed")
        check("fund account", data2.get("artifact", {}).get("total_count", 0) >= 1)

        # ── 异步回调模式 ──
        print("--- 异步回调模式 ---")
        import json as _json
        import threading
        import time as _time
        from http.server import BaseHTTPRequestHandler, HTTPServer

        received: dict = {}
        got_callback = threading.Event()

        class _CallbackHandler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                received.update(_json.loads(body))
                got_callback.set()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"success": true}')

            def log_message(self, *args):  # noqa: A002
                pass

        cb_server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        cb_port = cb_server.server_address[1]
        threading.Thread(target=cb_server.serve_forever, daemon=True).start()

        # 用 ASGITransport 在同一 event loop 驱动后台回调任务（TestClient 会取消后台任务）
        async def _run_async_test() -> dict:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=apps["housing"]),
                base_url="http://testserver",
                timeout=httpx.Timeout(5.0),
            ) as async_client:
                resp = await async_client.post("/tasks", json={
                    "task_id": "a2a_async_001",
                    "skill": "query_property",
                    "input": {"owner_name": "张三"},
                    "callback_url": f"http://127.0.0.1:{cb_port}/callback",
                })
                data = resp.json()
                # 轮询等回调（await asyncio.sleep 让事件循环驱动后台任务）
                deadline = _time.monotonic() + 5.0
                while not got_callback.is_set() and _time.monotonic() < deadline:
                    await asyncio.sleep(0.1)
                return {"data": data, "got": got_callback.is_set()}

        try:
            async_result = asyncio.run(_run_async_test())
            data = async_result["data"]
            check("异步模式立即返回 submitted", data.get("status") == "submitted")
            check("异步模式 artifact 为 None", data.get("artifact") is None)
            check("收到异步回调", async_result["got"], "5s 内未收到回调")
            check("回调状态 completed", received.get("status") == "completed")
            check("回调 artifact 有数据", received.get("artifact", {}).get("total_count", 0) >= 1)
            check("回调含签名/时间戳", "signature" in received and "timestamp" in received)
        finally:
            cb_server.shutdown()

        # ── 启动入口存在 ──
        check("start_servers 可调用", callable(start_servers))

        print(f"\n=== {passed}/{passed + failed} passed, {failed} failed ===")
        sys.exit(1 if failed else 0)

    main()
