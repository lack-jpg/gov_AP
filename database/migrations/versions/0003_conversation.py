"""add conversation + conversation_message tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-08

对应 database/models.py 的 Conversation / ConversationMessage:
    - conversation         多轮对话会话
    - conversation_message 对话消息（user / assistant）
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 conversation / conversation_message 表。"""
    op.create_table(
        "conversation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
    )
    op.create_index("ix_conversation_conversation_id", "conversation", ["conversation_id"])
    op.create_index("ix_conversation_user_id", "conversation", ["user_id"])

    op.create_table(
        "conversation_message",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_message_conversation_id", "conversation_message", ["conversation_id"])


def downgrade() -> None:
    """删除 conversation / conversation_message 表。"""
    op.drop_index("ix_conversation_message_conversation_id", table_name="conversation_message")
    op.drop_table("conversation_message")

    op.drop_index("ix_conversation_user_id", table_name="conversation")
    op.drop_index("ix_conversation_conversation_id", table_name="conversation")
    op.drop_table("conversation")
