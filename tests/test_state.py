"""
test_state - AgentState definition and helper function tests
"""
from __future__ import annotations

import pytest

from orchestration.langgraph.state import (
    AgentState,
    Evidence,
    IntentResult,
    MCPCallRecord,
    MCPCallStatus,
    MaterialCheckResult,
    PolicyResult,
    RiskLevel,
    Task,
    TaskStatus,
    add_evidence,
    add_task,
    clear_error,
    create_initial_state,
    record_mcp_call,
    set_error,
    set_final_answer,
    set_intent,
)


class TestEnums:
    def test_risk_level_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_task_status(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.COMPLETED.value == "completed"


class TestInitialState:
    def test_default_fields(self, initial_state):
        assert initial_state["user_query"] == "我想开一家餐馆需要什么手续"
        assert initial_state["intent"] == ""
        assert initial_state["task_plan"] == []
        assert initial_state["messages"] == []
        assert initial_state["mcp_history"] == []
        assert initial_state["risk_level"] == "low"
        assert initial_state["error"] == ""
        assert initial_state["retry_count"] == 0

    def test_trace_id_generated(self, initial_state):
        assert initial_state["trace_id"].startswith("trace_")

    def test_custom_trace_id(self):
        state = create_initial_state(user_query="test", trace_id="my_trace")
        assert state["trace_id"] == "my_trace"


class TestHelpers:
    def test_set_intent(self, initial_state):
        result = IntentResult(label="restaurant_license", label_name="餐饮许可", confidence=0.93)
        state = set_intent(initial_state, result)
        assert state["intent"] == "restaurant_license"
        assert state["intent_result"]["confidence"] == 0.93

    def test_add_task(self, initial_state):
        task = Task(type="search_policy", agent="policy", description="查询政策")
        from orchestration.langgraph.state import AgentName
        task = Task(type="search_policy", agent=AgentName.POLICY)
        state = add_task(initial_state, task)
        assert len(state["task_plan"]) == 1
        assert state["task_plan"][0]["type"] == "search_policy"

    def test_add_evidence(self, initial_state):
        ev = [Evidence(source="条例A", excerpt="规定X", relevance_score=0.9)]
        state = add_evidence(initial_state, ev)
        assert len(state["evidence"]) == 1
        assert state["evidence"][0]["source"] == "条例A"

    def test_record_mcp_call(self, initial_state):
        record = MCPCallRecord(
            trace_id=initial_state["trace_id"],
            server_name="policy_server",
            tool_name="search_policy",
        )
        state = record_mcp_call(initial_state, record)
        assert len(state["mcp_history"]) == 1
        assert state["mcp_history"][0]["tool_name"] == "search_policy"

    def test_set_error_and_clear(self, initial_state):
        state = set_error(initial_state, "test error")
        assert state["error"] == "test error"
        assert len(state["error_history"]) == 1

        state2 = clear_error(state)
        assert state2["error"] == ""
        assert state2["retry_count"] == 1

    def test_set_final_answer(self, initial_state):
        state = set_final_answer(initial_state, "回答")
        assert state["final_answer"] == "回答"


class TestPydanticModels:
    def test_policy_result(self):
        pr = PolicyResult(answer="需要营业执照", evidence=[], confidence=0.9)
        assert pr.confidence == 0.9

    def test_material_result(self):
        mr = MaterialCheckResult(passed=False, missing=["身份证"])
        assert mr.passed is False
        assert "身份证" in mr.missing

    def test_mcp_record_default_status(self):
        record = MCPCallRecord(trace_id="t", server_name="s", tool_name="tool")
        assert record.status == MCPCallStatus.SUCCESS
