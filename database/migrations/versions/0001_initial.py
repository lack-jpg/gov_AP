"""initial migration - create all core tables

Revision ID: 0001
Revises:
Create Date: 2026-08-02

对应 database/models.py + orchestration/langgraph/checkpointer.py 的全部表:
    - trace                  Agent 执行追踪
    - agent                  Agent 配置
    - prompt                 Prompt 版本
    - evaluation             评测结果
    - checkpoint             LangGraph 状态快照（A2A 恢复）
    - langgraph_checkpoints  LangGraph 原生 checkpoint
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建所有核心表。"""
    # ── trace ──
    op.create_table(
        "trace",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("span_id", sa.String(length=32), nullable=False),
        sa.Column("parent_span_id", sa.String(length=32), nullable=True),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("node_name", sa.String(length=64), nullable=True),
        sa.Column("input_data", sa.Text(), nullable=True),
        sa.Column("output_data", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=256), nullable=True),
        sa.Column("tool_input", sa.Text(), nullable=True),
        sa.Column("tool_output", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trace_trace_id", "trace", ["trace_id"])
    op.create_index("ix_trace_agent_name", "trace", ["agent_name"])

    # ── agent ──
    op.create_table(
        "agent",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id"),
    )
    op.create_index("ix_agent_name", "agent", ["name"])

    # ── prompt ──
    op.create_table(
        "prompt",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prompt_id", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prompt_id"),
    )
    op.create_index("ix_prompt_agent_name", "prompt", ["agent_name"])

    # ── evaluation ──
    op.create_table(
        "evaluation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eval_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("task_success_rate", sa.Float(), nullable=False),
        sa.Column("tool_accuracy", sa.Float(), nullable=False),
        sa.Column("rag_faithfulness", sa.Float(), nullable=False),
        sa.Column("rag_answer_relevance", sa.Float(), nullable=False),
        sa.Column("rag_context_recall", sa.Float(), nullable=False),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False),
        sa.Column("avg_step_count", sa.Float(), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=True),
        sa.Column("dataset_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eval_id"),
    )
    op.create_index("ix_evaluation_version", "evaluation", ["version"])

    # ── checkpoint（业务层 Checkpoint 表） ──
    op.create_table(
        "checkpoint",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("checkpoint_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("checkpoint_data", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_id"),
    )
    op.create_index("ix_checkpoint_task_id", "checkpoint", ["task_id"])
    op.create_index("ix_checkpoint_thread_id", "checkpoint", ["thread_id"])

    # ── langgraph_checkpoints（LangGraph 原生 checkpoint） ──
    op.create_table(
        "langgraph_checkpoints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=128), nullable=False),
        sa.Column("parent_checkpoint_id", sa.String(length=128), nullable=True),
        sa.Column("checkpoint_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_langgraph_checkpoints_thread_id",
        "langgraph_checkpoints", ["thread_id"],
    )
    op.create_index(
        "ix_langgraph_checkpoints_checkpoint_id",
        "langgraph_checkpoints", ["checkpoint_id"],
    )


def downgrade() -> None:
    """删除所有核心表。"""
    op.drop_index("ix_langgraph_checkpoints_checkpoint_id", table_name="langgraph_checkpoints")
    op.drop_index("ix_langgraph_checkpoints_thread_id", table_name="langgraph_checkpoints")
    op.drop_table("langgraph_checkpoints")

    op.drop_index("ix_checkpoint_thread_id", table_name="checkpoint")
    op.drop_index("ix_checkpoint_task_id", table_name="checkpoint")
    op.drop_table("checkpoint")

    op.drop_index("ix_evaluation_version", table_name="evaluation")
    op.drop_table("evaluation")

    op.drop_index("ix_prompt_agent_name", table_name="prompt")
    op.drop_table("prompt")

    op.drop_index("ix_agent_name", table_name="agent")
    op.drop_table("agent")

    op.drop_index("ix_trace_agent_name", table_name="trace")
    op.drop_index("ix_trace_trace_id", table_name="trace")
    op.drop_table("trace")
