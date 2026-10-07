"""Scope conversations to tenants and persist A2A checkpoint identity.

Unknown legacy ownership is quarantined using an empty tenant. Old unscoped
checkpoints and pending A2A tasks are deliberately not adopted automatically.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Backfill only known owners; never assign unidentified data to a tenant."""
    for table in ("conversation", "conversation_message"):
        op.add_column(table, sa.Column("tenant_id", sa.String(64), nullable=False, server_default=""))
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.execute(sa.text('''
        UPDATE conversation SET tenant_id = "user".tenant_id
        FROM "user" WHERE conversation.user_id = "user".username
    '''))
    op.execute(sa.text('''
        UPDATE conversation_message SET tenant_id = conversation.tenant_id
        FROM conversation
        WHERE conversation_message.conversation_id = conversation.conversation_id
    '''))
    for table in ("conversation", "conversation_message"):
        op.alter_column(table, "tenant_id", server_default=None)
    op.add_column("a2a_task", sa.Column("checkpoint_thread_id", sa.String(128), nullable=False, server_default=""))
    op.alter_column("a2a_task", "checkpoint_thread_id", server_default=None)


def downgrade() -> None:
    """Restore the preceding schema without changing conversation IDs."""
    op.drop_column("a2a_task", "checkpoint_thread_id")
    for table in ("conversation_message", "conversation"):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
