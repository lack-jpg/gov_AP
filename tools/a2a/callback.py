"""
a2a.callback - A2A Callback: receive and process async task completion notifications

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement callback endpoint for external agent task results
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status

from tools.logger import get_logger
from tools.a2a.protocol import A2ATaskResponse, A2ATaskStatus
from tools.a2a.task import get_task_store, TaskStore
from tools.a2a.registry import get_external_registry, ExternalAgentRegistry

logger = get_logger(__name__)


# ============================================================
# A2ACallbackHandler
# ============================================================


class A2ACallbackHandler:
    """
    A2A 回调处理器 — 接收外部 Agent 的异步任务完成通知。

    职责:
    1. 验证回调请求的合法性
    2. 查找对应的 A2A 任务记录
    3. 更新任务状态
    4. 恢复 LangGraph 执行（通过 Checkpoint 机制）

    流程:
        外部 Agent 完成 → POST /api/a2a/callback
            ↓
        A2ACallbackHandler.process_callback()
            ↓
        1. 验证 task_id 存在
            ↓
        2. 更新 TaskStore 中的任务状态
            ↓
        3. 通过 Checkpointer 查找挂起的 LangGraph checkpoint
            ↓
        4. 注入 external_result → 恢复执行
            ↓
        5. 返回处理结果

    用法:
        handler = A2ACallbackHandler()
        result = await handler.process_callback(
            task_id="a2a_abc123",
            status="completed",
            artifact={"result": "..."},
        )
    """

    def __init__(
        self,
        task_store: Optional[TaskStore] = None,
        registry: Optional[ExternalAgentRegistry] = None,
    ):
        """
        Args:
            task_store: 任务存储
            registry: 外部 Agent 注册中心
        """
        self._task_store = task_store or get_task_store()
        self._registry = registry or get_external_registry()

    # ── 核心接口 ──

    async def process_callback(
        self,
        task_id: str,
        status_str: str,
        artifact: Optional[dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        处理外部 Agent 回调。

        Args:
            task_id: A2A 任务 ID
            status_str: 任务状态字符串（completed | failed | timeout）
            artifact: 任务结果数据
            error_message: 错误信息

        Returns:
            {
                "success": True/False,
                "message": "...",
                "task_id": "a2a_xxx",
                "checkpoint_resumed": True/False,
                "final_state": {...} | None,
            }
        """
        # 1. 查找任务记录
        record = self._task_store.get(task_id)
        if record is None:
            logger.error("A2A 回调: 任务 {} 不存在", task_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found",
            )

        tsm = self._task_store.get_state_machine(task_id)
        if tsm is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"State machine for task {task_id} not found",
            )

        # 2. 解析状态
        try:
            new_status = A2ATaskStatus(status_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_str}. Valid: {[s.value for s in A2ATaskStatus]}",
            )

        # 幂等：终态收到相同的终态回调（重复/重试）→ 视为成功 no-op，不重复恢复
        if (
            new_status in (A2ATaskStatus.COMPLETED, A2ATaskStatus.FAILED, A2ATaskStatus.TIMEOUT)
            and tsm.status == new_status
        ):
            logger.info(
                "A2A 回调幂等命中: {task_id} 已是 {status}，忽略重复回调",
                task_id=task_id, status=new_status.value,
            )
            return {
                "success": True,
                "message": f"Callback already {new_status.value} (idempotent no-op)",
                "task_id": task_id,
                "checkpoint_resumed": False,
                "final_state": None,
            }

        # 3. 更新任务状态
        try:
            # 兼容外部 Agent 未单独通知 WORKING 的情况（submitted → completed/failed）
            if new_status in (A2ATaskStatus.COMPLETED, A2ATaskStatus.FAILED, A2ATaskStatus.TIMEOUT):
                if tsm.status == A2ATaskStatus.CREATED:
                    tsm.submit()
                if tsm.status == A2ATaskStatus.SUBMITTED:
                    tsm.start_working()

            if new_status == A2ATaskStatus.COMPLETED:
                tsm.complete(artifact or {})
                logger.info("A2A 回调: {task_id} → COMPLETED", task_id=task_id)
            elif new_status == A2ATaskStatus.FAILED:
                tsm.fail(error_message or "External agent reported failure")
                logger.warning("A2A 回调: {task_id} → FAILED", task_id=task_id)
            elif new_status == A2ATaskStatus.TIMEOUT:
                tsm.timeout(error_message or "External agent reported timeout")
                logger.warning("A2A 回调: {task_id} → TIMEOUT", task_id=task_id)
            else:
                # WORKING / SUBMITTED 等中间状态
                tsm.transition(new_status)
                logger.debug("A2A 回调: {task_id} → {status}", task_id=task_id, status=new_status.value)
        except Exception as e:
            logger.error("A2A 回调状态更新失败: {task_id} — {error}", task_id=task_id, error=e)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"State transition failed: {e}",
            )

        # 4. 尝试恢复 LangGraph（如果 checkpointer 可用）
        checkpoint_resumed = False
        final_state = None

        if new_status in (A2ATaskStatus.COMPLETED, A2ATaskStatus.FAILED):
            try:
                # 尝试从 Checkpointer 恢复执行
                checkpoint_resumed = await self._try_resume_graph(task_id, tsm.record)
            except Exception as e:
                logger.error("恢复 LangGraph 失败: {task_id} — {error}", task_id=task_id, error=e)
                # 不抛出 — 回调本身是成功的，恢复失败只记录日志

        return {
            "success": True,
            "message": f"Callback processed: {task_id} → {new_status.value}",
            "task_id": task_id,
            "checkpoint_resumed": checkpoint_resumed,
            "final_state": final_state,
        }

    # ── 内部 ──

    async def _try_resume_graph(self, task_id: str, record) -> bool:
        """
        尝试通过 Checkpointer 恢复 LangGraph 执行。

        Args:
            task_id: A2A 任务 ID
            record: 更新后的 A2ATaskRecord

        Returns:
            True 如果恢复成功
        """
        try:
            from orchestration.langgraph.checkpointer import PostgresCheckpointer
            from database.connection import get_session_factory

            # 检查数据库是否可用
            factory = get_session_factory()
            if factory is None:
                logger.debug("数据库不可用，跳过 LangGraph 恢复")
                return False

            checkpointer = PostgresCheckpointer()
            checkpoint_tuple = await checkpointer.resume_from_a2a(task_id)

            if checkpoint_tuple is None:
                logger.debug("未找到 A2A 挂起的 checkpoint: {task_id}", task_id=task_id)
                return False

            # 恢复执行
            # 注意: 实际的 graph.ainvoke 需要在有 graph 实例的上下文中执行
            # 此处只验证 checkpoint 存在，实际恢复由 AgentService 完成
            logger.info(
                "找到 A2A 挂起 checkpoint: thread={thread}, checkpoint={cp}",
                thread=checkpoint_tuple.config.get("configurable", {}).get("thread_id", "?"),
                cp=checkpoint_tuple.config.get("configurable", {}).get("checkpoint_id", "?"),
            )
            return True

        except ImportError:
            logger.debug("Checkpointer 模块不可用，跳过 LangGraph 恢复")
            return False
        except Exception as e:
            logger.error("恢复 LangGraph 异常: {}", e)
            return False


# ============================================================
# FastAPI Router — 供 backend 挂载
# ============================================================

from pydantic import BaseModel, Field as PydanticField


class CallbackRequest(BaseModel):
    """A2A 回调请求体（与 backend.api.schemas.A2ACallbackRequest 对应）"""

    task_id: str = PydanticField(description="A2A 任务 ID")
    status: str = PydanticField(description="任务状态: completed | failed | timeout")
    artifact: Optional[dict[str, Any]] = PydanticField(
        default=None, description="外部 Agent 返回的结果数据"
    )
    error_message: Optional[str] = PydanticField(
        default=None, description="失败时的错误信息"
    )


class CallbackResponse(BaseModel):
    """A2A 回调响应体"""

    success: bool = PydanticField(default=True, description="处理是否成功")
    message: str = PydanticField(default="callback processed", description="处理结果消息")
    task_id: str = PydanticField(default="", description="A2A 任务 ID")
    checkpoint_resumed: bool = PydanticField(default=False, description="是否恢复了 LangGraph")


def create_callback_router(handler: Optional[A2ACallbackHandler] = None) -> APIRouter:
    """
    创建 A2A Callback FastAPI Router。

    将被挂载到 backend 主应用上。

    Args:
        handler: A2ACallbackHandler 实例，不传则创建默认

    Returns:
        FastAPI APIRouter，包含 /callback 端点
    """
    if handler is None:
        handler = A2ACallbackHandler()

    router = APIRouter(prefix="/a2a", tags=["A2A Callback"])

    @router.post(
        "/callback",
        response_model=CallbackResponse,
        summary="A2A 外部 Agent 回调",
        description="接收外部 Agent（如不动产系统、公积金系统）的异步任务完成通知",
    )
    async def a2a_callback_endpoint(request: CallbackRequest) -> CallbackResponse:
        """
        A2A Callback 端点。

        外部 Agent 完成任务后回调此端点：
        1. 根据 task_id 找到原 A2A 任务记录
        2. 更新任务状态
        3. 尝试恢复 LangGraph 执行
        """
        result = await handler.process_callback(
            task_id=request.task_id,
            status_str=request.status,
            artifact=request.artifact,
            error_message=request.error_message,
        )
        return CallbackResponse(
            success=result["success"],
            message=result["message"],
            task_id=result["task_id"],
            checkpoint_resumed=result["checkpoint_resumed"],
        )

    return router


# ============================================================
# 全局单例
# ============================================================

_handler: Optional[A2ACallbackHandler] = None


def get_callback_handler() -> A2ACallbackHandler:
    """获取全局 A2ACallbackHandler 单例"""
    global _handler
    if _handler is None:
        _handler = A2ACallbackHandler()
    return _handler


# ============================================================
# Smoke Test — python -m tools.a2a.callback
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
        # 准备测试数据
        from tools.a2a.task import TaskStore
        from orchestration.langgraph.state import A2ATaskRecord, A2ATaskStatus as StateA2AStatus

        store = TaskStore()
        record = A2ATaskRecord(
            source_agent="workflow",
            target_agent="housing_agent",
            skill="query_property",
            input={"user_id": "001"},
        )
        tsm = store.create(record)
        tsm.submit()
        tsm.start_working()

        handler = A2ACallbackHandler(task_store=store)

        # ── 1. 成功回调 ──
        section("1. Process Callback — COMPLETED")
        result = await handler.process_callback(
            task_id=record.task_id,
            status_str="completed",
            artifact={"properties": [{"address": "测试地址"}]},
        )
        check("success == True", result["success"] is True)
        check("task_id returned", result["task_id"] == record.task_id)
        check("task status updated", tsm.status == A2ATaskStatus.COMPLETED)
        check("artifact saved", tsm.record.artifact == {"properties": [{"address": "测试地址"}]})

        # ── 2. 失败回调 ──
        section("2. Process Callback — FAILED")
        record2 = A2ATaskRecord(
            source_agent="workflow",
            target_agent="fund_agent",
            skill="query_fund",
            input={"user_id": "002"},
        )
        tsm2 = store.create(record2)
        tsm2.submit()
        tsm2.start_working()

        result2 = await handler.process_callback(
            task_id=record2.task_id,
            status_str="failed",
            error_message="External fund service unavailable",
        )
        check("fail callback success", result2["success"] is True)
        check("task FAILED", tsm2.status == A2ATaskStatus.FAILED)
        check("error_message saved",
              tsm2.record.error_message == "External fund service unavailable")

        # ── 3. 超时回调 ──
        section("3. Process Callback — TIMEOUT")
        record3 = A2ATaskRecord(
            source_agent="workflow",
            target_agent="housing_agent",
            skill="query_property",
            input={"property_id": "X-001"},
        )
        tsm3 = store.create(record3)
        tsm3.submit()
        tsm3.start_working()

        result3 = await handler.process_callback(
            task_id=record3.task_id,
            status_str="timeout",
            error_message="Request timed out after 30s",
        )
        check("timeout callback success", result3["success"] is True)
        check("task TIMEOUT", tsm3.status == A2ATaskStatus.TIMEOUT)

        # ── 4. 中间状态 ──
        section("4. Process Callback — WORKING (intermediate)")
        record4 = A2ATaskRecord(
            source_agent="workflow",
            target_agent="housing_agent",
            skill="query_property",
            input={"user_id": "003"},
        )
        tsm4 = store.create(record4)
        tsm4.submit()

        result4 = await handler.process_callback(
            task_id=record4.task_id,
            status_str="working",
        )
        check("intermediate callback success", result4["success"] is True)
        check("task WORKING", tsm4.status == A2ATaskStatus.WORKING)

        # ── 5. 错误处理 ──
        section("5. Error Handling")
        # 不存在的 task_id
        from fastapi import HTTPException
        try:
            await handler.process_callback(
                task_id="nonexistent_task",
                status_str="completed",
            )
            check("404 on unknown task", False, "Expected HTTPException")
        except HTTPException as e:
            check("404 on unknown task", e.status_code == 404)

        # 无效状态
        try:
            await handler.process_callback(
                task_id=record4.task_id,
                status_str="invalid_status",
            )
            check("400 on invalid status", False, "Expected HTTPException")
        except HTTPException as e:
            check("400 on invalid status", e.status_code == 400)

        # ── 6. Router 创建 ──
        section("6. Router Creation")
        router = create_callback_router(handler)
        check("router created", router is not None)
        check("router prefix == /a2a", router.prefix == "/a2a")
        # 找到 /callback 路由
        callback_routes = [r for r in router.routes if "/callback" in r.path]  # type: ignore[attr-defined]
        check("callback endpoint exists", len(callback_routes) > 0)

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            exit(1)
        else:
            print(" — all good")
            print(f"\n  Run with: python -m tools.a2a.callback")

    asyncio.run(main())
