"""
P1-8 PII 实际脱敏测试。

验证：含手机号/身份证的输入在进入 LLM 前被 mask_pii 脱敏，
      trace / 日志 / LLM prompt / MCP 参数均读取脱敏后的 state.user_query；
     governance_node 对输出侧同样脱敏，并合并入口 PII 审计类型。
"""
from __future__ import annotations

import pytest

import backend.api.dependencies as deps
from backend.config import get_settings


class _FakeRuntime:
    """捕获 execute_with_safeguards 收到的 initial_state。"""

    def __init__(self, captured: dict):
        self.captured = captured

    async def execute_with_safeguards(self, graph, initial_state, graph_config=None):
        self.captured["initial_state"] = initial_state
        return initial_state


@pytest.mark.asyncio
async def test_execute_agent_masks_pii_before_llm(monkeypatch):
    """execute_agent：入口护栏后，user_query 以脱敏值进入 graph。"""
    captured: dict = {}

    async def fake_graph(settings):
        return object()  # 运行时为 fake，graph 不被真正使用

    from orchestration.langgraph import runtime as rt

    monkeypatch.setattr(deps, "get_agent_graph", fake_graph)
    monkeypatch.setattr(
        rt, "create_runtime_from_settings",
        lambda settings: _FakeRuntime(captured),
    )

    result = await deps.execute_agent(
        user_query="我的手机13812341234，身份证110101199001011234",
        user_id="u1",
        trace_id="trace_pii",
        settings=get_settings(),
    )

    initial_state = captured["initial_state"]
    # LLM / trace / 日志 / MCP 读到的 user_query 已脱敏
    assert "13812341234" not in initial_state["user_query"]
    assert "138****1234" in initial_state["user_query"]
    assert "110101199001011234" not in initial_state["user_query"]
    assert "110***********1234" in initial_state["user_query"]
    # 入口 PII 类型已预写入 safety_check，供 governance 审计
    assert "phone" in initial_state["safety_check"]["pii_detected"]
    assert "id_card" in initial_state["safety_check"]["pii_detected"]
    # 返回的最终 state 同样脱敏
    assert "13812341234" not in result["user_query"]


@pytest.mark.asyncio
async def test_stream_agent_masks_pii_before_llm(monkeypatch):
    """stream_agent：SSE 流式路径同样在 graph 前脱敏。"""
    captured: dict = {}

    class _FakeGraph:
        async def astream(self, initial_state, config=None, stream_mode="values"):
            captured["initial_state"] = initial_state
            yield initial_state

    async def fake_graph(settings):
        return _FakeGraph()

    monkeypatch.setattr(deps, "get_agent_graph", fake_graph)

    events = []
    async for kind, payload in deps.stream_agent(
        user_query="联系我 13812341234",
        user_id="u1",
        trace_id="trace_sse_pii",
        settings=get_settings(),
    ):
        events.append((kind, payload))

    initial_state = captured["initial_state"]
    assert "13812341234" not in initial_state["user_query"]
    assert "138****1234" in initial_state["user_query"]
    assert "phone" in initial_state["safety_check"]["pii_detected"]
    assert events  # 至少产出 final 事件


@pytest.mark.asyncio
async def test_governance_node_masks_output_pii():
    """governance_node：输出侧脱敏 + 合并入口 PII 审计类型。"""
    from orchestration.langgraph.nodes import governance_node
    from orchestration.langgraph.state import create_initial_state
    from governance.trace import reset_trace_recorder

    reset_trace_recorder()

    state = create_initial_state(user_query="查询房产", trace_id="trace_gov")
    state["final_answer"] = "您的手机号是13812341234，请保持畅通。"
    state["safety_check"] = {"pii_detected": ["phone"]}

    result = await governance_node(state, llm=None)

    # 输出侧 PII 已脱敏
    assert "13812341234" not in result["final_answer"]
    assert "138****1234" in result["final_answer"]
    # 入口已脱敏 → detect_pii 找不到明文，但入口记录的 phone 类型被合并保留
    assert "phone" in result["safety_check"]["pii_detected"]
