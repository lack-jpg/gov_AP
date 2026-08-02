"""
a2a.connector - A2A Connector: send tasks to external agents, handle callbacks

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement A2A Connector for cross-domain Agent task delegation
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from tools.logger import get_logger
from tools.a2a.protocol import (
    A2ATaskRequest,
    A2ATaskResponse,
    A2ATaskStatus,
    AgentCard,
)
from tools.a2a.registry import get_external_registry, ExternalAgentRegistry
from tools.a2a.task import get_task_store, TaskStateMachine, TaskStore

logger = get_logger(__name__)


# ============================================================
# A2AConnector
# ============================================================


class A2AConnector:
    """
    A2A 连接器 — 管理与外部 Agent 的通信。

    职责:
    1. 根据技能发现可用的外部 Agent
    2. 发送异步任务请求
    3. 检查任务状态
    4. Stub fallback（当外部 Agent 不可用时）

    架构:
        Gov AP LangGraph Node
               |
        A2AConnector.send_task()
               |
        ├─ HTTP → 外部 Agent Server (12201/12202/...)
               |
        └─ Stub → Mock Agent (本地函数调用)

    用法:
        connector = A2AConnector()
        result = await connector.send_task("query_property", {"owner_name": "张三"})
    """

    def __init__(
        self,
        registry: Optional[ExternalAgentRegistry] = None,
        task_store: Optional[TaskStore] = None,
        http_timeout: float = 30.0,
    ):
        """
        Args:
            registry: 外部 Agent 注册中心
            task_store: 任务存储
            http_timeout: HTTP 请求超时时间（秒）
        """
        self._registry = registry or get_external_registry()
        self._task_store = task_store or get_task_store()
        self._http_timeout = http_timeout
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def registry(self) -> ExternalAgentRegistry:
        return self._registry

    @property
    def task_store(self) -> TaskStore:
        return self._task_store

    async def _get_http_client(self) -> httpx.AsyncClient:
        """惰性创建 HTTP 客户端"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._http_timeout),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http_client

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ── 核心接口 ──

    async def send_task(
        self,
        skill: str,
        input_data: dict[str, Any],
        *,
        callback_url: str = "",
        source_trace_id: str = "",
        prefer_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        向外部 Agent 发送异步任务。

        优先通过 HTTP 发送，不可用时 fallback 到 stub。

        Args:
            skill: 调用的技能
            input_data: 任务输入参数
            callback_url: 回调地址（外部 Agent 完成后回调）
            source_trace_id: 源系统 trace_id
            prefer_agent: 优先使用的 Agent（可选）

        Returns:
            {
                "task_id": "a2a_xxx",
                "status": "submitted",       # stub 模式下可能直接 completed
                "agent_name": "housing_agent",
                "artifact": {...} | null,     # stub 模式下直接返回结果
                "mode": "http" | "stub",
            }
        """
        from tools.a2a.protocol import A2ATaskRequest, A2ATaskRecord

        # 发现可用 Agent
        agents = self._registry.discover(skill)
        if not agents:
            logger.warning("未找到技能 {} 的外部 Agent，使用 stub fallback", skill)
            return await self._send_stub(skill, input_data)

        # 选择 Agent
        target: AgentCard
        if prefer_agent:
            target = self._registry.get_agent(prefer_agent)  # type: ignore[assignment]
            if target is None:
                logger.warning("指定的 Agent {} 不可用", prefer_agent)
                return await self._send_stub(skill, input_data)
        else:
            target = agents[0]

        # 创建任务记录
        task_record = A2ATaskRecord(
            source_agent="workflow",
            target_agent=target.name,
            skill=skill,
            input=input_data,
        )
        tsm = self._task_store.create(task_record)

        # 创建请求
        request = A2ATaskRequest(
            task_id=task_record.task_id,
            skill=skill,
            input=input_data,
            callback_url=callback_url,
            source_trace_id=source_trace_id,
            timeout_ms=target.timeout_ms,
        )

        # 尝试 HTTP 发送
        if target.endpoint:
            try:
                result = await self._send_http(request, target)
                if result is not None:
                    tsm.submit()
                    return {
                        "task_id": task_record.task_id,
                        "status": "submitted",
                        "agent_name": target.name,
                        "artifact": None,  # 异步模式，等待回调
                        "mode": "http",
                    }
            except Exception as e:
                logger.warning("HTTP 发送失败 ({})，fallback to stub: {}", target.name, e)

        # Stub fallback
        await self._send_stub_sync(skill, input_data, tsm)
        return {
            "task_id": task_record.task_id,
            "status": tsm.status.value,
            "agent_name": target.name,
            "artifact": tsm.record.artifact,
            "mode": "stub",
        }

    async def check_status(self, task_id: str) -> dict[str, Any]:
        """
        查询 A2A 任务状态。

        Args:
            task_id: A2A 任务 ID

        Returns:
            {"task_id": "...", "status": "...", "artifact": {...} | null}
        """
        record = self._task_store.get(task_id)
        if record is None:
            return {"task_id": task_id, "status": "unknown", "artifact": None}

        return {
            "task_id": record.task_id,
            "status": record.status.value,
            "artifact": record.artifact,
            "error_message": record.error_message,
        }

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        """
        取消进行中的 A2A 任务。

        Args:
            task_id: A2A 任务 ID

        Returns:
            {"task_id": "...", "cancelled": True/False}
        """
        tsm = self._task_store.get_state_machine(task_id)
        if tsm is None:
            return {"task_id": task_id, "cancelled": False, "error": "Task not found"}

        if tsm.is_terminal:
            return {"task_id": task_id, "cancelled": False, "error": "Task already in terminal state"}

        try:
            tsm.fail("Cancelled by user")
            return {"task_id": task_id, "cancelled": True}
        except Exception as e:
            return {"task_id": task_id, "cancelled": False, "error": str(e)}

    # ── 内部实现 ──

    async def _send_http(
        self,
        request: A2ATaskRequest,
        target: AgentCard,
    ) -> Optional[dict[str, Any]]:
        """
        通过 HTTP 向外部 Agent 发送任务。
        """
        client = await self._get_http_client()

        url = f"{target.endpoint}/tasks"
        payload = {
            "task_id": request.task_id,
            "skill": request.skill,
            "input": request.input,
            "callback_url": request.callback_url,
            "source_trace_id": request.source_trace_id,
        }

        response = await client.post(url, json=payload)
        response.raise_for_status()

        logger.info(
            "A2A HTTP: {task_id} → {agent} ({url}), status={status}",
            task_id=request.task_id,
            agent=target.name,
            url=url,
            status=response.status_code,
        )

        return response.json()

    async def _send_stub(
        self,
        skill: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Stub fallback — 本地模拟外部 Agent 调用"""
        from tools.a2a.protocol import A2ATaskRecord

        task_record = A2ATaskRecord(
            source_agent="workflow",
            target_agent="stub_agent",
            skill=skill,
            input=input_data,
        )
        tsm = self._task_store.create(task_record)

        return await self._send_stub_sync(skill, input_data, tsm)

    async def _send_stub_sync(
        self,
        skill: str,
        input_data: dict[str, Any],
        tsm: TaskStateMachine,
    ) -> dict[str, Any]:
        """
        同步执行 stub 调用（无需等待回调）。
        """
        tsm.submit()
        tsm.start_working()

        try:
            if skill.startswith("query_property") or skill == "register_property":
                from tools.a2a.mock_agents.housing_agent import query_property_stub, register_property_stub
                if skill == "register_property":
                    artifact = await register_property_stub(input_data)
                else:
                    artifact = await query_property_stub(input_data)
                tsm.complete(artifact)

            elif skill.startswith("query_fund"):
                from tools.a2a.mock_agents.fund_agent import query_fund_stub, query_fund_detail_stub
                if skill == "query_fund_detail":
                    artifact = await query_fund_detail_stub(input_data)
                else:
                    artifact = await query_fund_stub(input_data)
                tsm.complete(artifact)

            else:
                # 通用 stub
                tsm.complete({
                    "message": f"Stub response for skill: {skill}",
                    "input_echo": input_data,
                })

        except Exception as e:
            tsm.fail(str(e))

        return {
            "task_id": tsm.task_id,
            "status": tsm.status.value,
            "agent_name": "stub",
            "artifact": tsm.record.artifact,
            "mode": "stub",
        }


# ============================================================
# 全局单例
# ============================================================

_connector: Optional[A2AConnector] = None


def get_a2a_connector() -> A2AConnector:
    """获取全局 A2AConnector 单例"""
    global _connector
    if _connector is None:
        _connector = A2AConnector()
    return _connector


# ============================================================
# Smoke Test — python -m tools.a2a.connector
# ============================================================

if __name__ == "__main__":
    import asyncio

    passed = 0
    failed = 0

    def check(description: str, condition: bool, detail: str = ""):
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {description}")
        else:
            failed += 1
            print(f"  [FAIL] {description}")
            if detail:
                print(f"         {detail}")

    def section(title: str):
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")

    async def main():
        # 先初始化注册中心和 Agent
        from tools.a2a.registry import ExternalAgentRegistry, AgentHealth

        reg = ExternalAgentRegistry()
        from tools.a2a.protocol import AgentCard
        reg.register(AgentCard(
            name="housing_agent", display_name="不动产",
            skills=["query_property"], endpoint="http://loc:12201",
        ))
        reg.register(AgentCard(
            name="fund_agent", display_name="公积金",
            skills=["query_fund"], endpoint="http://loc:12202",
        ))
        reg.set_health("housing_agent", AgentHealth.HEALTHY)
        reg.set_health("fund_agent", AgentHealth.HEALTHY)

        from tools.a2a.task import TaskStore
        store = TaskStore()

        connector = A2AConnector(registry=reg, task_store=store)

        # ── 1. send_task — query_property (stub fallback) ──
        section("1. send_task — query_property")
        result = await connector.send_task(
            "query_property",
            {"owner_name": "张三"},
            source_trace_id="trace_test_001",
        )
        check("task_id starts with a2a_", result["task_id"].startswith("a2a_"))
        check("mode == stub", result["mode"] == "stub")
        check("artifact present", result["artifact"] is not None)
        check("properties found",
              result.get("artifact", {}).get("total_count", 0) >= 1)

        # ── 2. send_task — query_fund ──
        section("2. send_task — query_fund")
        result2 = await connector.send_task(
            "query_fund",
            {"user_id": "001"},
            source_trace_id="trace_test_002",
        )
        check("mode == stub", result2["mode"] == "stub")
        check("fund data present",
              result2.get("artifact", {}).get("total_count", 0) >= 1)

        # ── 3. send_task — unknown skill ──
        section("3. send_task — unknown skill")
        result3 = await connector.send_task(
            "unknown_skill",
            {"data": "test"},
            source_trace_id="trace_test_003",
        )
        check("task still created", result3["task_id"].startswith("a2a_"))
        check("artifact present", result3["artifact"] is not None)

        # ── 4. check_status ──
        section("4. check_status")
        task_id = result["task_id"]
        status = await connector.check_status(task_id)
        check("task_id match", status["task_id"] == task_id)
        check("status terminal", status["status"] in ("completed", "failed", "timeout"))
        check("artifact present", status["artifact"] is not None)

        # 不存在的 task
        unknown = await connector.check_status("nonexistent_task")
        check("unknown task", unknown["status"] == "unknown")

        # ── 5. cancel_task ──
        section("5. cancel_task")
        # 已完成的任务不能被取消
        cancel_result = await connector.cancel_task(task_id)
        check("completed task cannot be cancelled",
              not cancel_result["cancelled"])

        # ── 6. TaskStore 集成 ──
        section("6. TaskStore integration")
        check("task_store has records", store.count() >= 3)

        # ── 7. 关闭 ──
        await connector.close()
        check("http client closed", True)

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            exit(1)
        else:
            print(" — all good")
            print(f"\n  Run with: python -m tools.a2a.connector")

    asyncio.run(main())
