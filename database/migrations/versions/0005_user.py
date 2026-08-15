"""add user table

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-15

对应 database/models.py 的 User:
    - user  平台登录用户（bcrypt 密码哈希，用户名密码登录 → 签发 JWT）
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 user 表。"""
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_user_username", "user", ["username"])
    op.create_index("ix_user_tenant_id", "user", ["tenant_id"])


def downgrade() -> None:
    """删除 user 表。"""
    op.drop_index("ix_user_tenant_id", table_name="user")
    op.drop_index("ix_user_username", table_name="user")
    op.drop_table("user")
