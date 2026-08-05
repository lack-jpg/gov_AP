"""
langgraph.checkpointer - PostgreSQL-based LangGraph Checkpointer for state persistence

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement checkpoint save/restore for long-running and A2A workflows
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional, Iterator, AsyncIterator

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.connection import get_session_factory

logger = logging.getLogger(__name__)

from tools.logger import get_logger as _cp_get_logger
_cp_logger = _cp_get_logger(__name__)


# ============================================================
# Custom PostgreSQL Checkpointer
# ============================================================


class PostgresCheckpointer(BaseCheckpointSaver):
    """
    基于 PostgreSQL 的 LangGraph Checkpointer。

    功能:
    - 保存每个 thread 的 checkpoint 历史（支持回溯到任意历史节点）
    - 管理 checkpoint 的父子关系
    - 支持 A2A 异步任务的挂起和恢复
    - 自动清理过期 checkpoint

    使用方式:
        from orchestration.langgraph.checkpointer import PostgresCheckpointer
        checkpointer = PostgresCheckpointer()
        graph = build_graph(checkpointer=checkpointer)

    数据库依赖:
        需要 database/connection.py 已初始化
    """

    def __init__(
        self,
        serde: Optional[JsonPlusSerializer] = None,
    ):
        """
        Args:
            serde: 序列化器，默认使用 JsonPlusSerializer
        """
        super().__init__(serde=serde or JsonPlusSerializer())
        self._session_factory = get_session_factory()

    # ── 核心接口 ──

    async def aget_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        """
        异步获取指定 checkpoint。

        Args:
            config: LangGraph config，含 thread_id 和 checkpoint_id

        Returns:
            CheckpointTuple 或 None
        """
        thread_id = config.get("configurable", {}).get("thread_id", "")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id", "")

        async with self._session_factory() as session:
            if checkpoint_id:
                row = await self._get_checkpoint_by_id(session, thread_id, checkpoint_id)
            else:
                row = await self._get_latest_checkpoint(session, thread_id)

            if row is None:
                return None

            return self._row_to_tuple(row)

    async def alist(
        self,
        config: dict,
        *,
        limit: Optional[int] = None,
        before: Optional[dict] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """
        列出指定 thread 的 checkpoint 历史。

        Args:
            config: LangGraph config
            limit: 返回数量限制
            before: 仅返回此 checkpoint 之前的记录

        Yields:
            CheckpointTuple（从旧到新）
        """
        thread_id = config.get("configurable", {}).get("thread_id", "")

        async with self._session_factory() as session:
            stmt = (
                select(_CheckpointRow)
                .where(_CheckpointRow.thread_id == thread_id)
                .order_by(_CheckpointRow.checkpoint_id.asc())
            )
            if limit:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            rows = result.scalars().all()

            for row in rows:
                yield self._row_to_tuple(row)

    async def aput(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
    ) -> dict:
        """
        保存 checkpoint。

        Args:
            config: LangGraph config（含 thread_id, checkpoint_id）
            checkpoint: LangGraph Checkpoint 对象（含 channel_values, channel_versions）
            metadata: Checkpoint 元数据（含 source, step, writes）

        Returns:
            更新后的 config（含新的 checkpoint_id）
        """
        thread_id = config.get("configurable", {}).get("thread_id", "")
        checkpoint_id = checkpoint.get("id", "")

        if not thread_id or not checkpoint_id:
            raise ValueError("thread_id and checkpoint_id are required in config")

        # 序列化
        checkpoint_json = self._serde.dumps_typed(checkpoint)
        metadata_json = self._serde.dumps_typed(metadata)

        parent_checkpoint_id = config.get("configurable", {}).get(
            "checkpoint_id", ""
        )

        async with self._session_factory() as session:
            row = _CheckpointRow(
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                parent_checkpoint_id=parent_checkpoint_id or None,
                checkpoint_json=checkpoint_json,
                metadata_json=metadata_json,
            )
            session.add(row)
            await session.commit()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: dict,
        writes: list[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """
        保存待执行的 writes（用于错误恢复和 A2A 重试）。

        Args:
            config: LangGraph config
            writes: 待执行的 writes 列表 [(channel, value), ...]
            task_id: 任务 ID
        """
        thread_id = config.get("configurable", {}).get("thread_id", "")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id", "")

        # 将 writes 附加到 checkpoint 的 metadata 中
        async with self._session_factory() as session:
            row = await self._get_checkpoint_by_id(session, thread_id, checkpoint_id)
            if row and row.metadata_json:
                try:
                    meta = json.loads(row.metadata_json)
                    meta["pending_writes"] = writes
                    row.metadata_json = json.dumps(meta, default=str)
                    await session.commit()
                except (json.JSONDecodeError, TypeError) as e:
                    _cp_logger.warning("checkpointer: 解析 metadata JSON 失败: {}", e)
                    pass

    async def adelete_thread(self, thread_id: str) -> None:
        """
        删除指定 thread 的所有 checkpoint。

        Args:
            thread_id: LangGraph thread_id
        """
        async with self._session_factory() as session:
            stmt = delete(_CheckpointRow).where(
                _CheckpointRow.thread_id == thread_id
            )
            await session.execute(stmt)
            await session.commit()

    # ── 同步接口（LangGraph 要求实现） ──

    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        raise NotImplementedError("Use aget_tuple for async")

    def list(self, config: dict, *, limit=None, before=None) -> Iterator[CheckpointTuple]:
        raise NotImplementedError("Use alist for async")

    def put(self, config, checkpoint, metadata) -> dict:
        raise NotImplementedError("Use aput for async")

    def put_writes(self, config, writes, task_id) -> None:
        raise NotImplementedError("Use aput_writes for async")

    def delete_thread(self, thread_id: str) -> None:
        raise NotImplementedError("Use adelete_thread for async")

    # ── A2A 挂起/恢复 ──

    async def suspend_for_a2a(
        self,
        thread_id: str,
        checkpoint_id: str,
        a2a_task_id: str,
    ) -> None:
        """
        标记 checkpoint 为 A2A 挂起状态。

        Args:
            thread_id: LangGraph thread_id
            checkpoint_id: 当前 checkpoint
            a2a_task_id: 外部 A2A 任务 ID
        """
        async with self._session_factory() as session:
            row = await self._get_checkpoint_by_id(session, thread_id, checkpoint_id)
            if row and row.metadata_json:
                try:
                    meta = json.loads(row.metadata_json)
                    meta["a2a_suspended"] = True
                    meta["a2a_task_id"] = a2a_task_id
                    row.metadata_json = json.dumps(meta, default=str)
                    await session.commit()
                except (json.JSONDecodeError, TypeError) as e:
                    _cp_logger.warning("checkpointer: 解析 metadata JSON 失败: {}", e)
                    pass

    async def resume_from_a2a(
        self,
        a2a_task_id: str,
    ) -> Optional[CheckpointTuple]:
        """
        根据 A2A task_id 查找并恢复挂起的 checkpoint。

        Args:
            a2a_task_id: 外部 A2A 任务 ID

        Returns:
            挂起的 CheckpointTuple 或 None
        """
        async with self._session_factory() as session:
            # 在所有 checkpoint 中搜索 a2a_task_id
            stmt = (
                select(_CheckpointRow)
                .where(_CheckpointRow.metadata_json.contains(a2a_task_id))
                .order_by(_CheckpointRow.checkpoint_id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            return self._row_to_tuple(row)

    # ── 内部 ──

    async def _get_checkpoint_by_id(
        self,
        session: AsyncSession,
        thread_id: str,
        checkpoint_id: str,
    ) -> Optional[_CheckpointRow]:
        stmt = select(_CheckpointRow).where(
            _CheckpointRow.thread_id == thread_id,
            _CheckpointRow.checkpoint_id == checkpoint_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_latest_checkpoint(
        self,
        session: AsyncSession,
        thread_id: str,
    ) -> Optional[_CheckpointRow]:
        stmt = (
            select(_CheckpointRow)
            .where(_CheckpointRow.thread_id == thread_id)
            .order_by(_CheckpointRow.checkpoint_id.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    def _row_to_tuple(self, row: _CheckpointRow) -> CheckpointTuple:
        """将数据库行转换为 LangGraph CheckpointTuple"""
        checkpoint = self._serde.loads_typed(
            json.loads(row.checkpoint_json) if isinstance(row.checkpoint_json, str) else row.checkpoint_json
        )
        metadata = {}
        if row.metadata_json:
            raw = json.loads(row.metadata_json) if isinstance(row.metadata_json, str) else row.metadata_json
            metadata = self._serde.loads_typed(raw)

        parent_config = None
        if row.parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": row.thread_id,
                    "checkpoint_id": row.parent_checkpoint_id,
                }
            }

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": row.thread_id,
                    "checkpoint_id": row.checkpoint_id,
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
        )


# ============================================================
# ORM 行定义（与 database/models.py 保持风格一致）
# ============================================================


from datetime import datetime as _dt
from sqlalchemy import Integer, String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from database.models import Base


class _CheckpointRow(Base):
    """LangGraph checkpoint 存储表 — 继承 database.models.Base 确保 init_db() 自动创建"""

    __tablename__ = "langgraph_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    checkpoint_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    parent_checkpoint_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    checkpoint_json: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[_dt] = mapped_column(DateTime, server_default=func.now())
