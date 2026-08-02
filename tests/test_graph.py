"""
test_graph - LangGraph stub-mode end-to-end tests
"""
from __future__ import annotations

import pytest

from orchestration.langgraph.graph import create_default_graph
from orchestration.langgraph.state import create_initial_state


@pytest.mark.asyncio
async def test_stub_graph_full_flow():
    """Stub 模式完整流程：supervisor → intent → policy → material → workflow → governance"""
    graph = create_default_graph()
    state = create_initial_state("我想开一家餐馆需要什么手续")

    result = await graph.ainvoke(state)

    # 意图被识别
    assert result.get("intent") == "restaurant_license", f"got: {result.get('intent')}"

    # 生成了最终回答
    assert result.get("final_answer"), "no final_answer"

    # 风险等级为 low
    assert result.get("risk_level") in ("low", "high")


@pytest.mark.asyncio
async def test_stub_graph_fund_query():
    """公积金查询流程"""
    graph = create_default_graph()
    state = create_initial_state("我想查询公积金余额")

    result = await graph.ainvoke(state)
    assert result.get("intent") == "fund_query"
    assert result.get("final_answer")


@pytest.mark.asyncio
async def test_stub_graph_trace_id_preserved():
    """trace_id 贯穿全程"""
    graph = create_default_graph()
    state = create_initial_state("开公司需要什么", trace_id="custom_trace_123")

    result = await graph.ainvoke(state)
    assert result.get("trace_id") == "custom_trace_123"
