"""add case table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-15

对应 database/models.py 的 Case:
    - case  政务办件记录（workflow_server 经数据库创建/查询，重启后仍在，P1-5）
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 case 表。"""
    op.create_table(
        "case",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("materials", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.String(length=256), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id"),
    )
    op.create_index("ix_case_case_id", "case", ["case_id"])
    op.create_index("ix_case_user_id", "case", ["user_id"])
    op.create_index("ix_case_tenant_id", "case", ["tenant_id"])
    op.create_index("ix_case_status", "case", ["status"])


def downgrade() -> None:
    """删除 case 表。"""
    op.drop_index("ix_case_status", table_name="case")
    op.drop_index("ix_case_tenant_id", table_name="case")
    op.drop_index("ix_case_user_id", table_name="case")
    op.drop_index("ix_case_case_id", table_name="case")
    op.drop_table("case")
