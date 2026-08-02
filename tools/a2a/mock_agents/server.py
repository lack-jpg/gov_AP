"""
a2a.mock_agents.server - A2A Mock HTTP Server: expose external agents as HTTP services

Author: le
Date: 2026/8/2
Version: 0.1
Task: Expose housing_agent / fund_agent as FastAPI HTTP endpoints for real A2A over HTTP

端口约定:
    12201 — housing_agent（不动产系统）
    12202 — fund_agent（公积金系统）

与 tools.a2a.registry.initialize_default_agents() 中注册的 endpoint 一致。

Usage:
    python -m tools.a2a.mock_agents.server                # 启动全部
    python -m tools.a2a.mock_agents.server --housing-port 12201
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any

from fastapi import FastAPI

from tools.a2a.protocol import A2ATaskRequest, A2ATaskResponse
from tools.logger import get_logger

logger = get_logger(__name__)


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
        接收 A2A 任务并同步执行。

        Args:
            request: A2A 任务请求（含 skill + input）

        Returns:
            A2A 任务响应
        """
        logger.info(
            "[{}] task={} skill={}",
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
    housing_port: int = 12201,
    fund_port: int = 12202,
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
    housing_port: int = 12201,
    fund_port: int = 12202,
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
    parser.add_argument("--housing-port", type=int, default=12201)
    parser.add_argument("--fund-port", type=int, default=12202)
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

        # ── 启动入口存在 ──
        check("start_servers 可调用", callable(start_servers))

        print(f"\n=== {passed}/{passed + failed} passed, {failed} failed ===")
        sys.exit(1 if failed else 0)

    main()
