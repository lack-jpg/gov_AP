"""
database.models - ORM models: trace, agent, prompt, evaluation, checkpoint tables

Author: le
Date: 2026/7/29
Version: 0.1
Task: Define SQLAlchemy ORM models for all core tables
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ============================================================
# Base
# ============================================================


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


def _utcnow() -> datetime:
    """返回当前 UTC 时间（作为列的默认值工厂）"""
    return datetime.now(timezone.utc)


def _uuid_hex() -> str:
    """生成无连字符的 UUID hex 字符串"""
    return uuid.uuid4().hex


# ============================================================
# Trace 表 — Agent 执行追踪
# ============================================================


class Trace(Base):
    """Agent 执行记录（全链路追踪）"""

    __tablename__ = "trace"

    # ── 主键 ──
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── 追踪标识 ──
    trace_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="全链路追踪ID"
    )
    span_id: Mapped[str] = mapped_column(
        String(32), nullable=False, default=_uuid_hex,
        comment="当前 span ID"
    )
    parent_span_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
        comment="父 span ID"
    )

    # ── Agent 信息 ──
    agent_name: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="Agent 名称: supervisor | intent | policy | material | workflow | governance"
    )
    node_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="LangGraph 节点名称"
    )

    # ── 输入输出 ──
    input_data: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Agent 输入（JSON 字符串）"
    )
    output_data: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Agent 输出（JSON 字符串）"
    )

    # ── 工具调用 ──
    tool_name: Mapped[str | None] = mapped_column(
        String(256), nullable=True,
        comment="调用的工具名称（如果是 MCP 调用）"
    )
    tool_input: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="工具调用参数（JSON 字符串）"
    )
    tool_output: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="工具调用返回（JSON 字符串）"
    )

    # ── 性能指标 ──
    latency_ms: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="执行耗时（毫秒）"
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="LLM 输入 Token 数"
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="LLM 输出 Token 数"
    )

    # ── 状态 ──
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running",
        comment="执行状态: running | success | failed | timeout"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="错误信息"
    )
    risk_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="low",
        comment="风险等级: low | medium | high | critical"
    )

    # ── 元数据 ──
    metadata_: Mapped[str | None] = mapped_column(
        "metadata", JSON, nullable=True,
        comment="扩展元数据（JSON）"
    )

    # ── 时间戳 ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
        comment="记录创建时间"
    )

    def __repr__(self) -> str:
        return f"<Trace(trace_id={self.trace_id!r}, agent={self.agent_name!r}, status={self.status!r})>"


# ============================================================
# Agent 表 — Agent 配置
# ============================================================


class Agent(Base):
    """Agent 配置记录"""

    __tablename__ = "agent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    agent_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default=_uuid_hex,
        comment="Agent 唯一标识"
    )
    name: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="Agent 名称: supervisor | intent | policy | material | workflow | governance"
    )
    version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="0.1.0",
        comment="Agent 版本号"
    )
    config: Mapped[str | None] = mapped_column(
        JSON, nullable=True,
        comment="Agent 配置（JSON）: {model, temperature, max_tokens, ...}"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active",
        comment="Agent 状态: active | inactive | testing"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Agent 描述"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<Agent(name={self.name!r}, version={self.version!r}, status={self.status!r})>"


# ============================================================
# Prompt 表 — Prompt 版本管理
# ============================================================


class Prompt(Base):
    """Prompt 版本记录"""

    __tablename__ = "prompt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    prompt_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default=_uuid_hex,
        comment="Prompt 唯一标识"
    )
    agent_name: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="关联的 Agent 名称"
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="Prompt 模板名称: SUPERVISOR_SYSTEM_PROMPT | PLANNER_PROMPT | ..."
    )
    version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="v1",
        comment="版本号: v1 | v2 | ..."
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Prompt 模板内容"
    )
    variables: Mapped[str | None] = mapped_column(
        JSON, nullable=True,
        comment="模板变量列表: ['user_query', 'intent', ...]"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="是否为当前活跃版本"
    )
    created_by: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="创建者"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<Prompt(name={self.name!r}, agent={self.agent_name!r}, version={self.version!r})>"


# ============================================================
# Evaluation 表 — 评测结果
# ============================================================


class Evaluation(Base):
    """Agent 评测结果"""

    __tablename__ = "evaluation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    eval_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default=_uuid_hex,
        comment="评测唯一标识"
    )
    version: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="被评测的版本号"
    )

    # ── 评测指标 ──
    task_success_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="任务成功率 (0.0~1.0)"
    )
    tool_accuracy: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="工具选择准确率 (0.0~1.0)"
    )
    rag_faithfulness: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="RAG 回答真实性 (0.0~1.0)"
    )
    rag_answer_relevance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="RAG 答案相关性 (0.0~1.0)"
    )
    rag_context_recall: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="RAG 上下文召回率 (0.0~1.0)"
    )
    avg_latency_ms: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="平均响应耗时（毫秒）"
    )
    avg_step_count: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="平均执行步数"
    )

    # ── 详情 ──
    total_cases: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="评测用例总数"
    )
    passed_cases: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="通过的用例数"
    )
    report_json: Mapped[str | None] = mapped_column(
        JSON, nullable=True,
        comment="完整评测报告（JSON）"
    )
    dataset_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="使用的数据集名称"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<Evaluation(version={self.version!r}, success_rate={self.task_success_rate})>"


# ============================================================
# Checkpoint 表 — LangGraph 状态持久化
# ============================================================


class Checkpoint(Base):
    """LangGraph 状态快照（用于 A2A 异步恢复和长流程持久化）"""

    __tablename__ = "checkpoint"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    checkpoint_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
        comment="Checkpoint 唯一标识"
    )
    task_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="关联的 A2A 任务 ID 或 trace_id"
    )
    thread_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="LangGraph thread_id"
    )

    # ── 状态数据 ──
    state_json: Mapped[str] = mapped_column(
        JSON, nullable=False,
        comment="完整的 AgentState JSON 快照"
    )
    checkpoint_data: Mapped[str | None] = mapped_column(
        JSON, nullable=True,
        comment="LangGraph 原生 checkpoint 数据"
    )

    # ── 状态 ──
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active",
        comment="Checkpoint 状态: active | resolved | expired"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<Checkpoint(id={self.checkpoint_id!r}, task={self.task_id!r}, status={self.status!r})>"
