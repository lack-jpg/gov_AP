"""
database.migrations.env - Alembic 环境配置

Author: le
Date: 2026/7/30
Version: 0.1
Task: Alembic migration environment — connects to PostgreSQL for schema migrations

Usage:
    alembic revision --autogenerate -m "description"   # 自动生成迁移
    alembic upgrade head                                # 执行所有迁移
    alembic downgrade -1                                # 回滚一步

注意：当前 Phase 使用 SQLAlchemy create_all() 进行表创建，
Alembic 留待后续 Phase（生产部署前）正式启用。
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config 对象
config = context.config

# 设置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── MetaData ──
# 导入所有 ORM 模型，使 autogenerate 能检测变更
from database.models import Base  # noqa: F401
from orchestration.langgraph.checkpointer import _CheckpointRow  # noqa: F401

target_metadata = Base.metadata


# ============================================================
# 迁移执行
# ============================================================


def run_migrations_offline() -> None:
    """
    离线模式：生成 SQL 脚本而非直接执行。

    用法: alembic upgrade head --sql > migration.sql
    """
    from backend.config import get_settings

    url = get_settings().postgres_sync_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    在线模式：直接连接数据库执行迁移。

    使用 SQLAlchemy async engine（通过 sync wrapper 或直接用 psycopg）。
    """
    from backend.config import get_settings

    settings = get_settings()

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=settings.postgres_sync_url,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
