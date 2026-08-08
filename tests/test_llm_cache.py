"""
test_llm_cache - LLM 响应缓存测试（不触网，patch 底层 ainvoke）
"""
from __future__ import annotations

import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from governance.llm_cache import CachingChatOpenAI, LlmCache


def _unique_model() -> str:
    """每次测试用唯一模型名，避免 Redis 跨运行缓存污染断言。"""
    return f"test-model-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_llm_cache_hit_reuses_result(monkeypatch):
    """相同消息第二次调用命中缓存，底层只调一次。"""
    calls = {"n": 0}

    async def fake_ainvoke(self, messages, config=None, **kwargs):
        calls["n"] += 1
        return AIMessage(content="fake-answer")

    monkeypatch.setattr("langchain_openai.ChatOpenAI.ainvoke", fake_ainvoke)

    llm = CachingChatOpenAI(
        model=_unique_model(), api_key="x", base_url="http://localhost:1/v1",
    )
    msgs = [SystemMessage(content="sys"), HumanMessage(content="相同问题")]

    r1 = await llm.ainvoke(msgs)
    r2 = await llm.ainvoke(msgs)

    assert r1.content == "fake-answer"
    assert r2.content == "fake-answer"
    assert calls["n"] == 1  # 第二次命中缓存，未调底层


@pytest.mark.asyncio
async def test_llm_cache_different_input_misses(monkeypatch):
    """不同输入不命中缓存。"""
    calls = {"n": 0}

    async def fake_ainvoke(self, messages, config=None, **kwargs):
        calls["n"] += 1
        return AIMessage(content=f"answer-{calls['n']}")

    monkeypatch.setattr("langchain_openai.ChatOpenAI.ainvoke", fake_ainvoke)

    llm = CachingChatOpenAI(
        model=_unique_model(), api_key="x", base_url="http://localhost:1/v1",
    )
    r1 = await llm.ainvoke([HumanMessage(content="问题A")])
    r2 = await llm.ainvoke([HumanMessage(content="问题B")])

    assert calls["n"] == 2
    assert r1.content == "answer-1"
    assert r2.content == "answer-2"


@pytest.mark.asyncio
async def test_cache_disabled_passthrough(monkeypatch):
    """禁用缓存时每次都调底层。"""
    calls = {"n": 0}

    async def fake_ainvoke(self, messages, config=None, **kwargs):
        calls["n"] += 1
        return AIMessage(content="x")

    monkeypatch.setattr("langchain_openai.ChatOpenAI.ainvoke", fake_ainvoke)

    llm = CachingChatOpenAI(
        model=_unique_model(), api_key="x", base_url="http://localhost:1/v1",
    )
    llm._cache_enabled = False

    await llm.ainvoke([HumanMessage(content="q")])
    await llm.ainvoke([HumanMessage(content="q")])
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_llm_cache_memory_fallback():
    """Redis 不可用时内存回退仍可用。"""
    cache = LlmCache(ttl=60)
    assert await cache.get("missing") is None
    await cache.set("k", "v")
    assert await cache.get("k") == "v"
