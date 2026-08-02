"""
database.redis - Redis async client: connection pool, cache operations, health check

Author: le
Date: 2026/7/30
Version: 0.1
Task: Implement Redis async client with connection management and basic cache ops
"""
from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis

from backend.config import Settings, get_settings
from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# Redis Client
# ============================================================


class RedisClient:
    """
    Redis 异步客户端封装。

    使用 redis-py 的 asyncio 接口（redis.asyncio），
    管理连接池生命周期，提供常用缓存操作。

    使用方式:
        client = RedisClient()
        await client.connect()
        await client.set("key", "value", ttl=3600)
        value = await client.get("key")
        await client.close()
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Args:
            settings: 应用配置，不传则用全局单例
        """
        self._settings = settings or get_settings()
        self._redis: Optional[aioredis.Redis] = None

    # ── 连接管理 ──

    async def connect(self) -> None:
        """建立 Redis 连接（创建连接池）"""
        if self._redis is not None:
            return

        self._redis = aioredis.from_url(
            self._settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )

        # 验证连接
        await self._redis.ping()
        logger.info(
            "Redis 已连接: {}:{}",
            self._settings.redis_host,
            self._settings.redis_port,
        )

    async def close(self) -> None:
        """关闭 Redis 连接"""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
            logger.info("Redis 连接已关闭")

    async def ping(self) -> bool:
        """健康检查：PING → PONG"""
        if self._redis is None:
            return False
        try:
            return await self._redis.ping()
        except Exception:
            return False

    # ── 基础缓存操作 ──

    async def get(self, key: str) -> Optional[str]:
        """
        获取缓存值。

        Args:
            key: 缓存键

        Returns:
            缓存值（字符串），不存在返回 None
        """
        if self._redis is None:
            raise RuntimeError("Redis 未连接，请先调用 connect()")
        return await self._redis.get(key)

    async def set(
        self, key: str, value: str, ttl: int = 3600
    ) -> bool:
        """
        设置缓存值。

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），默认 1 小时

        Returns:
            True
        """
        if self._redis is None:
            raise RuntimeError("Redis 未连接，请先调用 connect()")
        await self._redis.set(key, value, ex=ttl)
        return True

    async def delete(self, key: str) -> int:
        """
        删除缓存键。

        Args:
            key: 缓存键

        Returns:
            删除的键数量（0 或 1）
        """
        if self._redis is None:
            raise RuntimeError("Redis 未连接，请先调用 connect()")
        return await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        """
        检查键是否存在。

        Args:
            key: 缓存键

        Returns:
            是否存在
        """
        if self._redis is None:
            raise RuntimeError("Redis 未连接，请先调用 connect()")
        return bool(await self._redis.exists(key))

    async def ttl(self, key: str) -> int:
        """
        获取键的剩余过期时间。

        Args:
            key: 缓存键

        Returns:
            剩余秒数，-1 永不过期，-2 不存在
        """
        if self._redis is None:
            raise RuntimeError("Redis 未连接，请先调用 connect()")
        return await self._redis.ttl(key)

    async def incr(self, key: str, amount: int = 1) -> int:
        """
        原子递增。

        Args:
            key: 键
            amount: 增量

        Returns:
            递增后的值
        """
        if self._redis is None:
            raise RuntimeError("Redis 未连接，请先调用 connect()")
        return await self._redis.incrby(key, amount)

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._redis is not None


# ============================================================
# 模块级单例（惰性初始化）
# ============================================================

_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """获取或创建 Redis 客户端单例"""
    global _client
    if _client is None:
        _client = RedisClient()
    return _client


async def init_redis() -> None:
    """初始化 Redis 连接（应用启动时调用）"""
    try:
        client = get_redis_client()
        await client.connect()
    except Exception as e:
        logger.warning("Redis 初始化失败（将以无缓存模式运行）: {}", e)


async def close_redis() -> None:
    """关闭 Redis 连接（应用关闭时调用）"""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
