"""add trace.user_id / tenant_id (schema drift repair)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-06

背景（P4-6 验收发现）：
    Trace ORM（database/models.py）早已加入归属字段 user_id / tenant_id，
    但 0001 建表时未包含、后续也从未生成迁移 → 存量库 schema 漂移：
    trace 落库（governance/trace.py flush_to_db）INSERT 引用 user_id/tenant_id
    时抛 UndefinedColumnError，全部 span 滞留内存、DB trace 表恒为空。

本迁移：
    1. 为 trace 补充 user_id / tenant_id（NOT NULL，历史行以 '' 回填后移除 server_default，
       使 DB 列与 ORM 定义完全一致，避免后续 autogenerate 反复报 default 漂移）；
    2. 建立与模型一致的索引 ix_trace_user_id / ix_trace_tenant_id。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为 trace 补充归属列（幂等：仅当列不存在时添加，见 op 语义）。"""
    # 先以可空 + server_default 回填历史行，再收紧 NOT NULL 并移除 default，
    # 使 DB 列与 ORM 完全一致（避免 compare_server_default 漂移）。
    op.add_column(
        "trace",
        sa.Column("user_id", sa.String(length=64), nullable=True, server_default=""),
    )
    op.add_column(
        "trace",
        sa.Column("tenant_id", sa.String(length=64), nullable=True, server_default=""),
    )
    # 存量行回填为空字符串后收紧为 NOT NULL
    op.alter_column("trace", "user_id", nullable=False, server_default=None)
    op.alter_column("trace", "tenant_id", nullable=False, server_default=None)
    op.create_index("ix_trace_user_id", "trace", ["user_id"])
    op.create_index("ix_trace_tenant_id", "trace", ["tenant_id"])


def downgrade() -> None:
    """回滚：移除 trace 归属列与索引。"""
    op.drop_index("ix_trace_tenant_id", table_name="trace")
    op.drop_index("ix_trace_user_id", table_name="trace")
    op.drop_column("trace", "tenant_id")
    op.drop_column("trace", "user_id")
