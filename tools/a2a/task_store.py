"""
a2a.task_store - A2A Task PostgreSQL persistence store

Author: le
Date: 2026/8/8
Version: 0.1
Task: PostgresTaskStore — write-through durable A2A task store with in-memory mirror

设计:
    内存镜像为读源（与 TaskStore 相同的对象引用语义，TaskStateMachine 无需改动），
    每次 create / update / delete 及状态迁移都异步写穿到 a2a_task 表。
    每个任务一个 asyncio.Lock 串行写，保证写序；DB 不可用时自动降级为纯内存。

Usage:
    store = PostgresTaskStore()
    await store.hydrate()          # 启动时恢复存量任务（可选）
    tsm = store.create(record)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from tools.logger import get_logger
from tools.a2a.task import TaskStore, TaskStateMachine
from orchestration.langgraph.state import A2ATaskRecord, A2ATaskStatus

logger = get_logger(__name__)


# ============================================================
# 时间互转辅助（A2ATaskRecord 用 ISO 字符串，DB 用 datetime）
# ============================================================


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """ISO 8601 字符串 → timezone-aware datetime（None → None）"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    """datetime → ISO 8601 字符串（None → None）"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ============================================================
# PostgresTaskStore
# ============================================================


class PostgresTaskStore(TaskStore):
    """
    基于 PostgreSQL 的 A2A 任务存储（写穿式持久化）。

    继承 TaskStore 的内存实现，覆盖写路径增加 DB 写穿：
        - create(): 内存 + 立即写穿；返回带 on_change 持久化回调的 TaskStateMachine
        - update()/delete(): 内存 + 写穿
        - get_state_machine(): 内存命中返回，未命中由 hydrate() 预载覆盖（重启恢复）
        - hydrate(): 启动时从 a2a_task 全量载入内存

    DB 故障（连接失败/表不存在）时置 _db_enabled=False，之后仅内存运行并告警一次。
    """

    def __init__(self):
        super().__init__()
        self._db_enabled = True
        self._hydrated = False
        self._locks: dict[str, asyncio.Lock] = {}

    # ── 接口覆盖 ──

    def create(self, record: A2ATaskRecord) -> TaskStateMachine:
        """创建任务并立即写穿到 DB，返回带持久化回调的状态机。"""
        self._tasks[record.task_id] = record
        tsm = TaskStateMachine(record, on_change=self._schedule_upsert)
        self._state_machines[record.task_id] = tsm
        logger.info(
            "A2A 任务创建(持久化): {task_id} skill={skill}",
            task_id=record.task_id, skill=record.skill,
        )
        self._schedule_upsert(record)
        return tsm

    def get_state_machine(self, task_id: str) -> Optional[TaskStateMachine]:
        """内存命中返回；未命中返回 None（重启恢复依赖启动时 hydrate 预载）。"""
        return self._state_machines.get(task_id)

    def update(self, task_id: str, record: A2ATaskRecord) -> None:
        """更新内存并写穿。"""
        self._tasks[task_id] = record
        self._state_machines[task_id] = TaskStateMachine(record, on_change=self._schedule_upsert)
        self._schedule_upsert(record)

    def delete(self, task_id: str) -> None:
        """删除内存记录并写穿。"""
        self._tasks.pop(task_id, None)
        self._state_machines.pop(task_id, None)
        self._schedule_delete(task_id)

    # ── 启动恢复 ──

    async def hydrate(self) -> None:
        """
        从 a2a_task 表全量载入任务到内存并重建状态机（幂等）。

        在应用启动（lifespan）或首次构造 connector 时调用，保证重启后
        回调仍能按 task_id 找到原任务。
        """
        if self._hydrated:
            return
        self._hydrated = True
        if not self._db_enabled:
            return

        try:
            from database.connection import get_session_factory
            from database.models import A2ATask
            from sqlalchemy import select

            session_factory = get_session_factory()
            async with session_factory() as session:
                result = await session.execute(select(A2ATask))
                rows = result.scalars().all()

            loaded = 0
            for row in rows:
                if row.task_id not in self._tasks:
                    record = self._row_to_record(row)
                    self._tasks[record.task_id] = record
                    self._state_machines[record.task_id] = TaskStateMachine(
                        record, on_change=self._schedule_upsert,
                    )
                    loaded += 1
            if loaded:
                logger.info("A2A 任务从 DB 恢复: {} 条", loaded)
        except Exception as e:
            self._db_enabled = False
            logger.warning("A2A 任务 hydrate 失败，降级为内存模式: {}", e)

    # ── 写穿调度 ──

    def _schedule_upsert(self, record: A2ATaskRecord) -> None:
        """调度一次异步写穿（无运行 loop 时跳过，仅内存）。"""
        if not self._db_enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        task_id = record.task_id
        lock = self._locks.setdefault(task_id, asyncio.Lock())

        async def _do() -> None:
            async with lock:
                if not self._db_enabled:
                    return
                try:
                    await self._db_upsert(record)
                except Exception as e:
                    self._db_enabled = False
                    logger.warning(
                        "A2A 任务持久化失败，降级为内存模式: {task_id} — {error}",
                        task_id=task_id, error=e,
                    )

        loop.create_task(_do())

    def _schedule_delete(self, task_id: str) -> None:
        if not self._db_enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        lock = self._locks.setdefault(task_id, asyncio.Lock())

        async def _do() -> None:
            async with lock:
                if not self._db_enabled:
                    return
                try:
                    await self._db_delete(task_id)
                except Exception as e:
                    self._db_enabled = False
                    logger.warning(
                        "A2A 任务删除持久化失败，降级为内存模式: {task_id} — {error}",
                        task_id=task_id, error=e,
                    )

        loop.create_task(_do())

    # ── DB 操作 ──

    async def _db_upsert(self, record: A2ATaskRecord) -> None:
        from database.connection import get_session_factory
        from database.models import A2ATask
        from sqlalchemy.dialects.postgresql import insert

        session_factory = get_session_factory()
        stmt = insert(A2ATask).values(
            task_id=record.task_id,
            source_agent=record.source_agent,
            source_trace_id=record.source_trace_id,
            target_agent=record.target_agent,
            skill=record.skill,
            input_json=record.input,
            artifact=record.artifact,
            error_message=record.error_message,
            status=record.status.value,
            created_at=_parse_iso(record.created_at) or datetime.now(timezone.utc),
            completed_at=_parse_iso(record.completed_at),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[A2ATask.task_id],
            set_={
                "source_agent": stmt.excluded.source_agent,
                "source_trace_id": stmt.excluded.source_trace_id,
                "target_agent": stmt.excluded.target_agent,
                "skill": stmt.excluded.skill,
                "input_json": stmt.excluded.input_json,
                "artifact": stmt.excluded.artifact,
                "error_message": stmt.excluded.error_message,
                "status": stmt.excluded.status,
                "completed_at": stmt.excluded.completed_at,
            },
        )
        async with session_factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def _db_delete(self, task_id: str) -> None:
        from database.connection import get_session_factory
        from database.models import A2ATask
        from sqlalchemy import delete

        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(delete(A2ATask).where(A2ATask.task_id == task_id))
            await session.commit()

    def _row_to_record(self, row) -> A2ATaskRecord:
        """ORM 行 → A2ATaskRecord。"""
        return A2ATaskRecord(
            task_id=row.task_id,
            source_agent=row.source_agent,
            source_trace_id=row.source_trace_id,
            target_agent=row.target_agent,
            skill=row.skill,
            input=row.input_json or {},
            artifact=row.artifact,
            status=A2ATaskStatus(row.status) if row.status else A2ATaskStatus.CREATED,
            created_at=_to_iso(row.created_at) or "",
            completed_at=_to_iso(row.completed_at),
            error_message=row.error_message,
        )


# ============================================================
# Smoke Test — python -m tools.a2a.task_store [--with-db]
# ============================================================

if __name__ == "__main__":
    import sys

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

    async def main(with_db: bool) -> None:
        store = PostgresTaskStore()

        # ── 1. 内存接口 ──
        section("1. 内存接口")
        r1 = A2ATaskRecord(
            source_agent="workflow", source_trace_id="trace_001",
            target_agent="housing_agent", skill="query_property", input={"owner_name": "张三"},
        )
        r2 = A2ATaskRecord(
            source_agent="workflow", source_trace_id="trace_002",
            target_agent="fund_agent", skill="query_fund", input={"user_id": "001"},
        )
        tsm1 = store.create(r1)
        store.create(r2)
        check("create → count == 2", store.count() == 2)
        check("tsm 带 on_change", tsm1._on_change is not None)

        tsm1.submit()
        tsm1.start_working()
        check("迁移后 record 状态为 working", tsm1.record.status == A2ATaskStatus.WORKING)
        tsm1.complete({"property_count": 2})
        check("完成 → 终态", tsm1.record.status == A2ATaskStatus.COMPLETED)

        # ── 2. 状态机持久化回调触发（无 DB 时静默降级） ──
        section("2. 状态机写穿（尝试 DB，失败降级）")
        await asyncio.sleep(0.3)  # 给写穿任务一点执行时间
        check("store.get 返回更新后的 artifact", store.get(r1.task_id).artifact == {"property_count": 2})

        # ── 3. hydrate（DB 可用时验证持久化恢复） ──
        if with_db:
            section("3. hydrate（真实 DB）")
            store2 = PostgresTaskStore()
            await store2.hydrate()
            check("hydrate 后任务存在", store2.get(r1.task_id) is not None)
            check("hydrate 后状态为 completed", store2.get(r1.task_id).status == A2ATaskStatus.COMPLETED)
            store.delete(r1.task_id)
            store.delete(r2.task_id)
            await asyncio.sleep(0.3)
            store3 = PostgresTaskStore()
            await store3.hydrate()
            check("删除后 DB 无残留", store3.get(r1.task_id) is None and store3.get(r2.task_id) is None)
        else:
            section("3. hydrate（跳过，使用 --with-db 验证真实持久化）")
            print("  提示: python -m tools.a2a.task_store --with-db")

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            sys.exit(1)
        print(" — all good")

    asyncio.run(main(with_db="--with-db" in sys.argv))
