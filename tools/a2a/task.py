"""
a2a.task - A2A Task: task lifecycle management (created -> submitted -> working -> completed/failed)

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement A2A Task state machine and lifecycle management
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from tools.logger import get_logger
from orchestration.langgraph.state import A2ATaskStatus, A2ATaskRecord

logger = get_logger(__name__)


# ============================================================
# 状态转换表 — 定义合法的状态转换
# ============================================================

_VALID_TRANSITIONS: dict[A2ATaskStatus, set[A2ATaskStatus]] = {
    A2ATaskStatus.CREATED:   {A2ATaskStatus.SUBMITTED},
    A2ATaskStatus.SUBMITTED: {A2ATaskStatus.WORKING, A2ATaskStatus.FAILED, A2ATaskStatus.TIMEOUT},
    A2ATaskStatus.WORKING:   {A2ATaskStatus.COMPLETED, A2ATaskStatus.FAILED, A2ATaskStatus.TIMEOUT},
    A2ATaskStatus.COMPLETED: set(),   # 终态
    A2ATaskStatus.FAILED:    set(),   # 终态
    A2ATaskStatus.TIMEOUT:   set(),   # 终态
}

_TERMINAL_STATES: set[A2ATaskStatus] = {
    A2ATaskStatus.COMPLETED,
    A2ATaskStatus.FAILED,
    A2ATaskStatus.TIMEOUT,
}


# ============================================================
# TaskStateMachine
# ============================================================


class InvalidTransitionError(Exception):
    """非法状态转换异常"""
    pass


class TaskStateMachine:
    """
    A2A 任务状态机 — 管理单个 A2A 任务的生命周期。

    生命周期:
        CREATED → SUBMITTED → WORKING → COMPLETED / FAILED / TIMEOUT

    使用方式:
        tsm = TaskStateMachine(record)
        tsm.transition(A2ATaskStatus.SUBMITTED)
        tsm.transition(A2ATaskStatus.WORKING)
        tsm.transition(A2ATaskStatus.COMPLETED, artifact={...})
    """

    def __init__(
        self,
        record: A2ATaskRecord,
        *,
        on_change: Optional[Callable[[A2ATaskRecord], None]] = None,
    ):
        """
        Args:
            record: A2ATaskRecord 实例
            on_change: 可选回调，每次状态迁移后调用（用于持久化，如 PostgresTaskStore 写穿）
        """
        self._record = record
        self._on_change = on_change

    # ── 属性 ──

    @property
    def task_id(self) -> str:
        return self._record.task_id

    @property
    def status(self) -> A2ATaskStatus:
        return self._record.status

    @property
    def is_terminal(self) -> bool:
        return self._record.status in _TERMINAL_STATES

    @property
    def record(self) -> A2ATaskRecord:
        return self._record

    # ── 状态转换 ──

    def transition(
        self,
        new_status: A2ATaskStatus,
        artifact: Optional[dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> A2ATaskRecord:
        """
        将任务切换到新状态。

        Args:
            new_status: 目标状态
            artifact: 任务结果（仅 completed 时有效）
            error_message: 错误信息（failed/timeout 时有效）

        Returns:
            更新后的 A2ATaskRecord

        Raises:
            InvalidTransitionError: 非法状态转换
        """
        current = self._record.status

        if new_status not in _VALID_TRANSITIONS.get(current, set()):
            raise InvalidTransitionError(
                f"非法状态转换: {current.value} → {new_status.value} "
                f"(合法转换: {[s.value for s in _VALID_TRANSITIONS.get(current, set())]})"
            )

        self._record.status = new_status

        if artifact is not None:
            self._record.artifact = artifact

        if error_message is not None:
            self._record.error_message = error_message

        # 终态 → 记录完成时间
        if new_status in _TERMINAL_STATES:
            self._record.completed_at = datetime.now(timezone.utc).isoformat()

        logger.debug(
            "A2A {task_id}: {old} → {new}",
            task_id=self.task_id,
            old=current.value,
            new=new_status.value,
        )

        # 状态变更后触发持久化回调（PostgresTaskStore 写穿）
        if self._on_change is not None:
            try:
                self._on_change(self._record)
            except Exception as e:
                logger.warning("A2A 状态变更回调失败: {task_id} — {error}", task_id=self.task_id, error=e)

        return self._record

    def submit(self) -> A2ATaskRecord:
        """标记已提交给外部 Agent"""
        return self.transition(A2ATaskStatus.SUBMITTED)

    def start_working(self) -> A2ATaskRecord:
        """标记外部 Agent 开始处理"""
        return self.transition(A2ATaskStatus.WORKING)

    def complete(self, artifact: dict[str, Any]) -> A2ATaskRecord:
        """标记任务成功完成"""
        return self.transition(A2ATaskStatus.COMPLETED, artifact=artifact)

    def fail(self, error_message: str) -> A2ATaskRecord:
        """标记任务失败"""
        return self.transition(A2ATaskStatus.FAILED, error_message=error_message)

    def timeout(self, error_message: str = "Task timed out") -> A2ATaskRecord:
        """标记任务超时"""
        return self.transition(A2ATaskStatus.TIMEOUT, error_message=error_message)


# ============================================================
# TaskStore — 内存任务存储
# ============================================================


class TaskStore:
    """
    A2A 任务存储 — 内存 dict 实现。

    后续可用 RedisTaskStore 替换（相同接口）。

    使用方式:
        store = TaskStore()
        store.create(record)
        task = store.get(task_id)
        store.list_by_status(A2ATaskStatus.WORKING)
    """

    def __init__(self):
        self._tasks: dict[str, A2ATaskRecord] = {}
        self._state_machines: dict[str, TaskStateMachine] = {}

    def create(self, record: A2ATaskRecord) -> TaskStateMachine:
        """
        创建新任务并返回其状态机。

        Args:
            record: A2ATaskRecord 实例

        Returns:
            TaskStateMachine（可用于后续状态转换）
        """
        self._tasks[record.task_id] = record
        tsm = TaskStateMachine(record)
        self._state_machines[record.task_id] = tsm
        logger.info("A2A 任务创建: {task_id} skill={skill}", task_id=record.task_id, skill=record.skill)
        return tsm

    def get(self, task_id: str) -> Optional[A2ATaskRecord]:
        """按 task_id 获取任务记录"""
        return self._tasks.get(task_id)

    def get_state_machine(self, task_id: str) -> Optional[TaskStateMachine]:
        """按 task_id 获取状态机"""
        return self._state_machines.get(task_id)

    def update(self, task_id: str, record: A2ATaskRecord) -> None:
        """更新任务记录"""
        self._tasks[task_id] = record

    def delete(self, task_id: str) -> None:
        """删除任务记录"""
        self._tasks.pop(task_id, None)
        self._state_machines.pop(task_id, None)

    def list_all(self) -> list[A2ATaskRecord]:
        """列出所有任务"""
        return list(self._tasks.values())

    def list_by_status(self, status: A2ATaskStatus) -> list[A2ATaskRecord]:
        """按状态列出任务"""
        return [t for t in self._tasks.values() if t.status == status]

    def list_active(self) -> list[A2ATaskRecord]:
        """列出所有活跃（未终态）的任务"""
        return [t for t in self._tasks.values() if t.status not in _TERMINAL_STATES]

    def count(self) -> int:
        """任务总数"""
        return len(self._tasks)

    def count_by_status(self, status: A2ATaskStatus) -> int:
        """按状态统计任务数"""
        return len(self.list_by_status(status))


# ============================================================
# 全局单例
# ============================================================

_task_store: Optional[TaskStore] = None


def _create_default_store() -> TaskStore:
    """
    创建全局 TaskStore。

    DB 已配置且 PostgresTaskStore 可导入时返回持久化存储；
    否则回退到纯内存 TaskStore（无 DB 环境优雅降级）。
    """
    try:
        from tools.a2a.task_store import PostgresTaskStore
        from backend.config import get_settings

        settings = get_settings()
        if settings.postgres_host:
            return PostgresTaskStore()
    except Exception:
        pass
    return TaskStore()


def get_task_store() -> TaskStore:
    """获取全局 TaskStore 单例（DB 可用时自动持久化）"""
    global _task_store
    if _task_store is None:
        _task_store = _create_default_store()
    return _task_store


# ============================================================
# Smoke Test — python -m tools.a2a.task
# ============================================================

if __name__ == "__main__":
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

    # ── 1. 状态转换表 ──
    section("1. 转换表完整性")
    check("CREATED → SUBMITTED", A2ATaskStatus.SUBMITTED in _VALID_TRANSITIONS[A2ATaskStatus.CREATED])
    check("SUBMITTED → WORKING", A2ATaskStatus.WORKING in _VALID_TRANSITIONS[A2ATaskStatus.SUBMITTED])
    check("WORKING → COMPLETED", A2ATaskStatus.COMPLETED in _VALID_TRANSITIONS[A2ATaskStatus.WORKING])
    check("WORKING → FAILED", A2ATaskStatus.FAILED in _VALID_TRANSITIONS[A2ATaskStatus.WORKING])
    check("WORKING → TIMEOUT", A2ATaskStatus.TIMEOUT in _VALID_TRANSITIONS[A2ATaskStatus.WORKING])
    check("COMPLETED 无出边", len(_VALID_TRANSITIONS[A2ATaskStatus.COMPLETED]) == 0)
    check("终态包含 3 个", len(_TERMINAL_STATES) == 3)

    # ── 2. TaskStateMachine — 正常流程 ──
    section("2. TaskStateMachine — 正常流程")
    record = A2ATaskRecord(
        source_agent="workflow",
        target_agent="housing_agent",
        skill="query_property",
        input={"user_id": "001"},
    )
    tsm = TaskStateMachine(record)
    check("初始状态 == CREATED", tsm.status == A2ATaskStatus.CREATED)
    check("非终态", not tsm.is_terminal)

    tsm.submit()
    check("SUBMITTED", tsm.status == A2ATaskStatus.SUBMITTED)

    tsm.start_working()
    check("WORKING", tsm.status == A2ATaskStatus.WORKING)

    tsm.complete({"property_count": 2})
    check("COMPLETED", tsm.status == A2ATaskStatus.COMPLETED)
    check("is_terminal True", tsm.is_terminal)
    check("artifact saved", tsm.record.artifact == {"property_count": 2})
    check("completed_at set", tsm.record.completed_at is not None)

    # ── 3. TaskStateMachine — 非法转换 ──
    section("3. TaskStateMachine — 非法转换")
    record2 = A2ATaskRecord(
        source_agent="workflow",
        target_agent="fund_agent",
        skill="query_fund",
        input={"user_id": "002"},
    )
    tsm2 = TaskStateMachine(record2)

    # CREATED → COMPLETED 跳过中间状态
    try:
        tsm2.transition(A2ATaskStatus.COMPLETED)
        check("CREATED → COMPLETED 应被拒绝", False, "Expected InvalidTransitionError")
    except InvalidTransitionError:
        check("CREATED → COMPLETED 被拒绝", True)

    # COMPLETED → WORKING (逆行)
    tsm2.submit()
    tsm2.start_working()
    tsm2.complete({"result": "ok"})
    try:
        tsm2.transition(A2ATaskStatus.WORKING)
        check("COMPLETED → WORKING 应被拒绝", False, "Expected InvalidTransitionError")
    except InvalidTransitionError:
        check("COMPLETED → WORKING 被拒绝", True)

    # ── 4. TaskStateMachine — 失败流程 ──
    section("4. TaskStateMachine — 失败流程")
    record3 = A2ATaskRecord(
        source_agent="workflow",
        target_agent="housing_agent",
        skill="query_property",
        input={"property_id": "X-999"},
    )
    tsm3 = TaskStateMachine(record3)
    tsm3.submit()
    tsm3.start_working()
    tsm3.fail("External service unavailable")
    check("FAILED", tsm3.status == A2ATaskStatus.FAILED)
    check("error_message set", tsm3.record.error_message == "External service unavailable")
    check("is_terminal", tsm3.is_terminal)

    # ── 5. TaskStateMachine — 超时流程 ──
    section("5. TaskStateMachine — 超时流程")
    record4 = A2ATaskRecord(
        source_agent="workflow",
        target_agent="fund_agent",
        skill="query_fund",
        input={"user_id": "003"},
    )
    tsm4 = TaskStateMachine(record4)
    tsm4.submit()
    tsm4.timeout()
    check("TIMEOUT", tsm4.status == A2ATaskStatus.TIMEOUT)
    check("is_terminal", tsm4.is_terminal)
    check("default error_message", "timed out" in tsm4.record.error_message.lower())

    # ── 6. TaskStore ──
    section("6. TaskStore")
    store = TaskStore()

    r1 = A2ATaskRecord(source_agent="workflow", target_agent="housing_agent",
                       skill="query_property", input={"user_id": "A"})
    r2 = A2ATaskRecord(source_agent="workflow", target_agent="fund_agent",
                       skill="query_fund", input={"user_id": "B"})

    tsm_r1 = store.create(r1)
    store.create(r2)
    check("store.count == 2", store.count() == 2)

    tsm_r1.submit()
    tsm_r1.start_working()
    check("list_by_status WORKING == 1", len(store.list_by_status(A2ATaskStatus.WORKING)) == 1)
    check("list_active == 2", len(store.list_active()) == 2)

    tsm_r1.complete({"result": "ok"})
    check("list_active == 1 after 1 done", len(store.list_active()) == 1)

    stored = store.get(r1.task_id)
    check("store.get returns correct", stored is not None and stored.artifact == {"result": "ok"})

    store.delete(r2.task_id)
    check("store.count == 1 after delete", store.count() == 1)

    # ── 7. 全局单例 ──
    section("7. 全局单例")
    ts1 = get_task_store()
    ts2 = get_task_store()
    check("单例一致", ts1 is ts2)

    # ── Summary ──
    section("SUMMARY")
    total = passed + failed
    print(f"\n  {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
        exit(1)
    else:
        print(" — all good")
        print(f"\n  Run with: python -m tools.a2a.task")
