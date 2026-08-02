"""
database.connection - Database connection pool: PostgreSQL async connection with SQLAlchemy

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement async database connection and session management
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import Settings, get_settings


# ============================================================
# Engine & Session Factory
# ============================================================


def create_engine(settings: Settings) -> AsyncEngine:
    """
    创建异步 SQLAlchemy 引擎。

    Args:
        settings: 应用配置

    Returns:
        AsyncEngine 实例
    """
    return create_async_engine(
        settings.postgres_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,     # 每次从池中取出连接时先 ping 验证
        echo=settings.debug,     # debug 模式打印 SQL
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    创建异步 session 工厂。

    Args:
        engine: AsyncEngine 实例

    Returns:
        async_sessionmaker
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,   # 提交后不使对象过期（避免后续访问触发 lazy load）
    )


# ============================================================
# 模块级单例（惰性初始化）
# ============================================================

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """获取或惰性创建全局引擎单例"""
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings())
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取或惰性创建全局 session factory 单例"""
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


# ============================================================
# FastAPI 依赖注入
# ============================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖：获取异步数据库会话，自动提交/回滚/关闭。

    用法:
        @app.get("/data")
        async def endpoint(db: AsyncSession = Depends(get_db)): ...

    工作流:
        请求进入 → 创建 session → yield session → 请求处理 →
        提交(成功) 或 回滚(异常) → 关闭 session
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ============================================================
# 初始化
# ============================================================


async def init_db() -> None:
    """
    初始化数据库表。

    在应用启动时调用一次，创建所有 ORM 模型对应的表。
    不会删除已有数据（使用 create_all）。

    注意：需显式导入 checkpointer 以确保 langgraph_checkpoints 表被注册到 Base.metadata。
    """
    from database.models import Base
    # 确保 checkpointer 的 _CheckpointRow 表也被注册（延迟导入避免循环引用）
    from orchestration.langgraph.checkpointer import _CheckpointRow  # noqa: F401
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """关闭数据库连接池（应用关闭时调用）"""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
