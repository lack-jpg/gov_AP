"""add a2a_task table - A2A task state persistence

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08

对应 database/models.py 的 A2ATask:
    - a2a_task                A2A 跨域任务状态持久化（TaskStore 的 PostgreSQL 层）
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 a2a_task 表。"""
    op.create_table(
        "a2a_task",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("source_agent", sa.String(length=64), nullable=False),
        sa.Column("source_trace_id", sa.String(length=128), nullable=False),
        sa.Column("target_agent", sa.String(length=64), nullable=False),
        sa.Column("skill", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("artifact", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_a2a_task_task_id", "a2a_task", ["task_id"])
    op.create_index("ix_a2a_task_source_trace_id", "a2a_task", ["source_trace_id"])
    op.create_index("ix_a2a_task_skill", "a2a_task", ["skill"])
    op.create_index("ix_a2a_task_status", "a2a_task", ["status"])


def downgrade() -> None:
    """删除 a2a_task 表。"""
    op.drop_index("ix_a2a_task_status", table_name="a2a_task")
    op.drop_index("ix_a2a_task_skill", table_name="a2a_task")
    op.drop_index("ix_a2a_task_source_trace_id", table_name="a2a_task")
    op.drop_index("ix_a2a_task_task_id", table_name="a2a_task")
    op.drop_table("a2a_task")
