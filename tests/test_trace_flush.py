"""
P2-1 Trace 落库闭环测试。

验证：
1. start_trace_with_id 让整条 Agent 调用链的 span 归属请求级 trace_id；
2. flush_to_db 将 span 批量写入 Trace 表（含 user_id/tenant_id）；
3. flush_trace_to_db 落库成功后从内存清理该 trace 的 span；
4. execute_agent 请求结束后以请求 trace_id 触发落库。
"""
from __future__ import annotations

import pytest

import backend.api.dependencies as deps
from backend.config import get_settings


def test_agent_tracer_uses_request_trace_id():
    """start_trace_with_id 后，AgentTracer span 继承请求 trace_id 与父 span 关联。"""
    from governance.trace import (
        AgentTracer,
        SpanKind,
        end_trace,
        get_trace_recorder,
        reset_trace_recorder,
        start_trace_with_id,
    )

    reset_trace_recorder()
    start_trace_with_id("trace_req_1")
    try:
        with AgentTracer.span_sync(agent_name="supervisor", kind=SpanKind.AGENT) as span:
            span.record_output("ok")
    finally:
        end_trace()

    spans = get_trace_recorder().spans
    assert len(spans) == 1
    assert spans[0].trace_id == "trace_req_1"
    assert spans[0].parent_span_id is not None  # 挂到请求根 span 下


@pytest.mark.asyncio
async def test_flush_to_db_writes_user_tenant_and_clears(monkeypatch):
    """flush_to_db 批量写入 Trace 表（含 user_id/tenant_id），成功后清理内存。"""
    from governance.trace import (
        end_trace,
        flush_trace_to_db,
        get_trace_recorder,
        record_llm_usage,
        reset_trace_recorder,
        reset_trace_user,
        set_trace_user,
        start_trace_with_id,
    )

    reset_trace_recorder()
    sink: dict = {}

    class _Session:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            sink["rows"] = list(self.added)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Factory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr("database.connection.get_session_factory", lambda: _Factory())

    tokens = set_trace_user("user_1", "tenant_9")
    start_trace_with_id("trace_flush_1")
    try:
        record_llm_usage(agent_name="supervisor", input_tokens=10, output_tokens=5)
    finally:
        end_trace()
        reset_trace_user(tokens)

    written = await flush_trace_to_db("trace_flush_1")

    assert written == 1
    rows = sink["rows"]
    assert len(rows) == 1
    assert rows[0].trace_id == "trace_flush_1"
    assert rows[0].user_id == "user_1"
    assert rows[0].tenant_id == "tenant_9"
    assert rows[0].agent_name == "supervisor"
    # 落库成功后内存已清理，避免无界增长
    assert get_trace_recorder().get_spans_by_trace("trace_flush_1") == []


@pytest.mark.asyncio
async def test_execute_agent_flushes_request_trace(monkeypatch):
    """execute_agent 请求结束后以请求 trace_id 批量落库，span 归属请求 trace_id + 用户。"""
    from governance.trace import get_trace_recorder, record_llm_usage, reset_trace_recorder

    reset_trace_recorder()
    captured: dict = {}

    async def fake_graph(settings):
        return object()

    from orchestration.langgraph import runtime as rt

    class _FakeRuntime:
        async def execute_with_safeguards(self, graph, initial_state, graph_config=None):
            # 模拟节点执行期间记录一次 LLM span
            record_llm_usage(agent_name="supervisor", input_tokens=1, output_tokens=1)
            return initial_state

    monkeypatch.setattr(deps, "get_agent_graph", fake_graph)
    monkeypatch.setattr(rt, "create_runtime_from_settings", lambda settings: _FakeRuntime())

    async def fake_flush(trace_id):
        captured["trace_id"] = trace_id
        return 1

    import governance.trace as gt

    monkeypatch.setattr(gt, "flush_trace_to_db", fake_flush)

    await deps.execute_agent(
        user_query="查政策",
        user_id="u1",
        trace_id="trace_flush_chain",
        settings=get_settings(),
    )

    # 落库入口被以请求 trace_id 调用
    assert captured.get("trace_id") == "trace_flush_chain"
    # 执行期间记录的 span 归属请求 trace_id 与用户
    spans = get_trace_recorder().get_spans_by_trace("trace_flush_chain")
    assert len(spans) == 1
    assert spans[0].trace_id == "trace_flush_chain"
    assert spans[0].user_id == "u1"
