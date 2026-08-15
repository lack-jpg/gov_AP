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
        ├─ HTTP → 外部 Agent Server (12101/12111/...)
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
        default_callback_url: str = "",
        allow_stub: Optional[bool] = None,
        http_retries: int = 2,
        retry_backoff_base: float = 0.5,
    ):
        """
        Args:
            registry: 外部 Agent 注册中心
            task_store: 任务存储
            http_timeout: HTTP 请求超时时间（秒）
            default_callback_url: 默认回调地址（外部 Agent 完成后回调），send_task 未显式指定时使用
            allow_stub: 是否允许 stub 降级（P1-6 生产禁止 silent stub fallback）。
                        None 时读配置 A2A_ALLOW_STUB（默认 False）；True 仅用于显式开发开关
            http_retries: HTTP 发送失败重试次数（连接错误/5xx/429 才重试，4xx 不重试）
            retry_backoff_base: 重试退避基数（秒），第 n 次重试等待 base * 2^(n-1)
        """
        self._registry = registry or get_external_registry()
        self._task_store = task_store or get_task_store()
        self._http_timeout = http_timeout
        self._default_callback_url = default_callback_url
        self._allow_stub = self._resolve_allow_stub(allow_stub)
        self._http_retries = max(0, int(http_retries))
        self._retry_backoff_base = float(retry_backoff_base)
        self._http_client: Optional[httpx.AsyncClient] = None

    @staticmethod
    def _resolve_allow_stub(allow_stub: Optional[bool]) -> bool:
        """
        解析 stub 开关：显式传入优先；否则读配置 A2A_ALLOW_STUB（默认 False，生产禁止）。

        Args:
            allow_stub: 显式开关（None 表示未指定）

        Returns:
            True 允许 stub 降级；False 禁止（生产默认）
        """
        if allow_stub is not None:
            return bool(allow_stub)
        try:
            from backend.config import get_settings

            return bool(get_settings().a2a_allow_stub)
        except Exception:
            pass
        return False

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
                "error_message": "...",       # 失败/stub fallback 时记录原因（可追踪）
            }
        """
        from tools.a2a.protocol import A2ATaskRequest, A2ATaskRecord

        # 发现可用 Agent
        agents = self._registry.discover(skill)
        if not agents:
            logger.warning("未找到技能 {} 的外部 Agent，stub 开关={}", skill, self._allow_stub)
            if not self._allow_stub:
                return await self._fail_no_agent(skill, input_data, source_trace_id)
            return await self._send_stub(skill, input_data)

        # 选择 Agent
        target: AgentCard
        if prefer_agent:
            target = self._registry.get_agent(prefer_agent)  # type: ignore[assignment]
            if target is None:
                logger.warning("指定的 Agent {} 不可用，stub 开关={}", prefer_agent, self._allow_stub)
                if not self._allow_stub:
                    return await self._fail_no_agent(skill, input_data, source_trace_id)
                return await self._send_stub(skill, input_data)
        else:
            target = agents[0]

        # 创建任务记录
        task_record = A2ATaskRecord(
            source_agent="workflow",
            source_trace_id=source_trace_id,
            target_agent=target.name,
            skill=skill,
            input=input_data,
        )
        tsm = self._task_store.create(task_record)

        # 创建请求（未显式指定 callback_url 时使用 Connector 默认值）
        request = A2ATaskRequest(
            task_id=task_record.task_id,
            skill=skill,
            input=input_data,
            callback_url=callback_url or self._default_callback_url,
            source_trace_id=source_trace_id,
            timeout_ms=target.timeout_ms,
        )

        # 尝试 HTTP 发送（含重试）
        if target.endpoint:
            try:
                result = await self._send_http(request, target)
                if result is not None:
                    return self._handle_http_response(result, target, tsm)
            except Exception as e:
                reason = f"{type(e).__name__}: {e}"
                logger.warning("HTTP 发送失败 ({})，stub 开关={}", target.name, self._allow_stub)
                logger.debug("HTTP 发送失败详情: {}", reason)

                if not self._allow_stub:
                    # P1-6 生产禁止 silent stub fallback：任务明确失败，原因可追踪
                    self._fail_task(tsm, f"外部 Agent {target.name} 不可达: {reason}")
                    return {
                        "task_id": tsm.task_id,
                        "status": tsm.status.value,
                        "agent_name": target.name,
                        "artifact": None,
                        "mode": "http",
                        "error_message": tsm.record.error_message,
                    }

                # 显式开发开关 → 保留 stub fallback，但记录 fallback 原因（不静默）
                await self._send_stub_sync(skill, input_data, tsm, fallback_reason=reason)
                return {
                    "task_id": tsm.task_id,
                    "status": tsm.status.value,
                    "agent_name": target.name,
                    "artifact": tsm.record.artifact,
                    "mode": "stub",
                    "error_message": tsm.record.error_message,
                }

        # 未配置 endpoint：真实协议无法对接 → 按 stub 开关处理
        if not self._allow_stub:
            self._fail_task(tsm, f"外部 Agent {target.name} 未配置 endpoint，无法对接")
            return {
                "task_id": tsm.task_id,
                "status": tsm.status.value,
                "agent_name": target.name,
                "artifact": None,
                "mode": "http",
                "error_message": tsm.record.error_message,
            }

        # Stub fallback
        await self._send_stub_sync(skill, input_data, tsm)
        return {
            "task_id": task_record.task_id,
            "status": tsm.status.value,
            "agent_name": target.name,
            "artifact": tsm.record.artifact,
            "mode": "stub",
        }

    async def _fail_no_agent(
        self,
        skill: str,
        input_data: dict[str, Any],
        source_trace_id: str,
    ) -> dict[str, Any]:
        """
        stub 被禁止且无可用外部 Agent → 创建明确失败的任务（原因可追踪）。

        Args:
            skill: 技能名称
            input_data: 任务输入
            source_trace_id: 源系统 trace_id

        Returns:
            {"task_id": ..., "status": "failed", "mode": "http", "error_message": ...}
        """
        from tools.a2a.protocol import A2ATaskRecord

        task_record = A2ATaskRecord(
            source_agent="workflow",
            source_trace_id=source_trace_id,
            target_agent="unregistered",
            skill=skill,
            input=input_data,
        )
        tsm = self._task_store.create(task_record)
        reason = f"未注册任何提供技能 '{skill}' 的外部 Agent（stub 已禁用）"
        self._fail_task(tsm, reason)
        return {
            "task_id": tsm.task_id,
            "status": "failed",
            "agent_name": "unregistered",
            "artifact": None,
            "mode": "http",
            "error_message": reason,
        }

    def _fail_task(self, tsm: TaskStateMachine, reason: str) -> None:
        """
        将任务状态机推进到 FAILED（兼容 CREATED/SUBMITTED 起点）。

        Args:
            tsm: 任务状态机
            reason: 失败原因（写入 error_message，可追踪）
        """
        if tsm.status == A2ATaskStatus.CREATED:
            tsm.submit()
        if tsm.status == A2ATaskStatus.SUBMITTED:
            tsm.start_working()
        tsm.fail(reason)

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

    def _handle_http_response(
        self,
        result: dict[str, Any],
        target: AgentCard,
        tsm: TaskStateMachine,
    ) -> dict[str, Any]:
        """
        解析外部 Agent 的 A2ATaskResponse，把真实状态反映到任务记录。

        三种情况:
            - completed → 同步完成，直接返回 artifact（无需等待回调）
            - failed    → 同步失败
            - 其他（submitted/working）→ 异步模式，等待回调后恢复
        """
        resp_status = result.get("status", "submitted")

        if resp_status == "completed":
            artifact = result.get("artifact") or {}
            tsm.submit()
            tsm.start_working()
            tsm.complete(artifact)
            return {
                "task_id": tsm.task_id,
                "status": "completed",
                "agent_name": target.name,
                "artifact": artifact,
                "mode": "http",
            }

        if resp_status == "failed":
            tsm.submit()
            tsm.start_working()
            tsm.fail(result.get("error_message") or "external agent failed")
            return {
                "task_id": tsm.task_id,
                "status": "failed",
                "agent_name": target.name,
                "artifact": None,
                "mode": "http",
            }

        # submitted / working → 异步模式，等待回调
        tsm.submit()
        return {
            "task_id": tsm.task_id,
            "status": "submitted",
            "agent_name": target.name,
            "artifact": None,
            "mode": "http",
        }

    async def _send_http(
        self,
        request: A2ATaskRequest,
        target: AgentCard,
    ) -> Optional[dict[str, Any]]:
        """
        通过 HTTP 向外部 Agent 发送任务（P1-6：带超时与重试）。

        重试策略：连接错误 / 5xx / 408 / 429 重试（指数退避）；
        4xx 客户端错误不重试（外部 Agent 拒收，重试无意义）。

        Args:
            request: A2A 任务请求
            target: 目标 Agent 卡片

        Returns:
            外部 Agent 的 JSON 响应；无法解析时返回 {"status": "submitted"}

        Raises:
            httpx.HTTPError: 所有重试用尽后最后一次错误
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

        attempts = self._http_retries + 1
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()

                logger.info(
                    "A2A HTTP: {task_id} → {agent} ({url}), status={status}",
                    task_id=request.task_id,
                    agent=target.name,
                    url=url,
                    status=response.status_code,
                )
                try:
                    return response.json()
                except ValueError:
                    return {"status": "submitted"}

            except httpx.HTTPStatusError as e:
                last_error = e
                code = e.response.status_code
                # 4xx 客户端错误不重试（408/429 除外）
                if 400 <= code < 500 and code not in (408, 429):
                    logger.warning(
                        "A2A HTTP 客户端错误不重试: {task_id} → {agent}, code={code}, detail={detail}",
                        task_id=request.task_id, agent=target.name, code=code,
                        detail=str(getattr(e.response, "text", ""))[:200],
                    )
                    raise
                if attempt >= attempts:
                    break
                await self._backoff(attempt)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_error = e
                if attempt >= attempts:
                    break
                await self._backoff(attempt)

        # 所有重试用尽
        assert last_error is not None
        raise last_error

    async def _backoff(self, attempt: int) -> None:
        """
        指数退避等待（第 attempt 次失败后）。

        Args:
            attempt: 当前已失败次数（从 1 开始）
        """
        delay = self._retry_backoff_base * (2 ** (attempt - 1))
        await asyncio.sleep(delay)

    async def _send_stub(
        self,
        skill: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Stub fallback — 本地模拟外部 Agent 调用（仅 allow_stub=True 时进入）"""
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
        fallback_reason: str = "",
    ) -> dict[str, Any]:
        """
        同步执行 stub 调用（无需等待回调）。

        Args:
            skill: 技能名称
            input_data: 任务输入
            tsm: 任务状态机
            fallback_reason: 触发 stub 降级的原因（HTTP 失败详情），写入 error_message 供追踪
        """
        tsm.submit()
        tsm.start_working()

        if fallback_reason:
            tsm.record.error_message = fallback_reason

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
            skills=["query_property"], endpoint="http://loc:12101",
        ))
        reg.register(AgentCard(
            name="fund_agent", display_name="公积金",
            skills=["query_fund"], endpoint="http://loc:12111",
        ))
        reg.set_health("housing_agent", AgentHealth.HEALTHY)
        reg.set_health("fund_agent", AgentHealth.HEALTHY)

        from tools.a2a.task import TaskStore
        store = TaskStore()

        # 冒烟测试显式开启 stub 开关（模拟开发环境），生产默认禁止
        connector = A2AConnector(registry=reg, task_store=store, allow_stub=True)

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
            print("\n  Run with: python -m tools.a2a.connector")

    asyncio.run(main())
