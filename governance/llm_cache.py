"""
governance.llm_cache - LLM 响应缓存：相同问题复用结果，降低延迟与调用成本

Author: le
Date: 2026/8/8
Version: 0.1
Task: Implement Redis-first LLM response cache with in-memory fallback

设计:
    LlmCache        异步缓存（Redis 优先 + 内存 TTL 回退，失败静默降级内存）
    CachingChatOpenAI   ChatOpenAI 子类，覆写 ainvoke —— 以渲染后消息内容哈希为键

    生产环境 6 处 LLM 调用（planner/synthesizer/policy/generator/intent/router）
    都走 get_agent_graph 构造的同一个 LLM 实例，包一层即全覆盖。

    注意: 缓存命中不会触发 TokenUsageCallback（不记账 token），属可接受折衷；
          评测 harness 自建 ChatOpenAI，不经过缓存，评测走真实 LLM。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Optional, Sequence

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from backend.config import get_settings
from tools.logger import get_logger

logger = get_logger(__name__)

_PREFIX = "llmc:"


# ============================================================
# LlmCache — Redis 优先 + 内存回退
# ============================================================


class LlmCache:
    """
    LLM 响应缓存。

    - Redis 可用时写入/读取 Redis（key 前缀 `llmc:`，TTL 默认 1h）
    - Redis 不可用/未连接时回退到进程内 dict（带 TTL）
    - 所有失败静默降级，不阻断 LLM 调用
    """

    def __init__(self, ttl: int = 3600):
        self._ttl = ttl
        self._mem: dict[str, tuple[float, str]] = {}  # key -> (expiry_ts, value)
        self._redis_ok: Optional[bool] = None  # None=未探测, True/False

    async def get(self, key: str) -> Optional[str]:
        """读取缓存值（内存优先，其次 Redis）。"""
        # 内存
        mem = self._mem.get(key)
        if mem is not None:
            expiry, value = mem
            if expiry > time.time():
                return value
            self._mem.pop(key, None)

        # Redis
        client = await self._redis_client()
        if client is not None:
            try:
                value = await client.get(_PREFIX + key)
                if value is not None:
                    # 回填内存，加速后续读
                    self._mem[key] = (time.time() + self._ttl, value)
                    return value
            except Exception as e:
                self._redis_ok = False
                logger.debug("LLM 缓存 Redis 读取失败，降级内存: {}", e)

        return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """写入缓存（内存 + Redis best-effort）。"""
        ttl = ttl or self._ttl
        self._mem[key] = (time.time() + ttl, value)

        client = await self._redis_client()
        if client is not None:
            try:
                await client.set(_PREFIX + key, value, ttl=ttl)
            except Exception as e:
                self._redis_ok = False
                logger.debug("LLM 缓存 Redis 写入失败，仅内存: {}", e)

    # ── 内部 ──

    async def _redis_client(self):
        """惰性获取 Redis 客户端；失败一次后不再尝试。"""
        if self._redis_ok is False:
            return None
        try:
            from database.redis import get_redis_client

            client = get_redis_client()
            if not client.is_connected:
                await client.connect()
            self._redis_ok = True
            return client
        except Exception as e:
            self._redis_ok = False
            logger.debug("LLM 缓存 Redis 不可用，使用内存模式: {}", e)
            return None


# ============================================================
# CachingChatOpenAI — 带缓存的 ChatOpenAI
# ============================================================


def _message_text(message: Any) -> str:
    """提取消息文本（兼容 content 为 str 或 content blocks 列表）。"""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


class CachingChatOpenAI(ChatOpenAI):
    """
    ChatOpenAI 子类：对相同渲染消息命中缓存，直接返回历史结果。

    用法与 ChatOpenAI 完全一致，仅在 get_agent_graph 里替换构造类即可。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        settings = get_settings()
        self._cache_enabled = bool(settings.llm_cache_enabled)
        self._cache_ttl = int(settings.llm_cache_ttl)
        self._cache = LlmCache(ttl=self._cache_ttl)
        if self._cache_enabled:
            logger.info("LLM 响应缓存已启用 (ttl={}s)", self._cache_ttl)

    def _cache_key(self, messages: Sequence) -> str:
        """缓存键 = 模型名 + 渲染后消息内容哈希（不含 trace_id）。"""
        model = getattr(self, "model_name", "") or getattr(self, "model", "")
        payload = json.dumps([_message_text(m) for m in messages], ensure_ascii=False)
        return hashlib.sha256(f"{model}|{payload}".encode("utf-8")).hexdigest()

    async def ainvoke(self, messages, config=None, **kwargs) -> AIMessage:
        """带缓存的异步调用。"""
        if not self._cache_enabled:
            return await super().ainvoke(messages, config=config, **kwargs)

        key = self._cache_key(messages)
        try:
            cached = await self._cache.get(key)
        except Exception:
            cached = None

        if cached is not None:
            return AIMessage(content=cached)

        response = await super().ainvoke(messages, config=config, **kwargs)
        if isinstance(getattr(response, "content", None), str) and response.content:
            try:
                await self._cache.set(key, response.content)
            except Exception:
                pass
        return response
