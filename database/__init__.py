"""
database - PostgreSQL database layer: connection, ORM models, Redis cache, migrations

Author: le
Date: 2026/7/30
Version: 0.2
Task: Database package initialization — exports ORM models, connection utilities, and Redis client
"""
from __future__ import annotations

from database.connection import (
    create_engine,
    create_session_factory,
    get_engine,
    get_session_factory,
    get_db,
    init_db,
    close_db,
)
from database.redis import (
    RedisClient,
    get_redis_client,
    init_redis,
    close_redis,
)

__all__ = [
    # Connection
    "create_engine",
    "create_session_factory",
    "get_engine",
    "get_session_factory",
    "get_db",
    "init_db",
    "close_db",
    # Redis
    "RedisClient",
    "get_redis_client",
    "init_redis",
    "close_redis",
]
