"""Fail-closed checks for workflow case ids and policy answers."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agents.workflow.agent import WorkflowAgent, WorkflowUnavailable
from orchestration.langgraph.nodes import policy_node
from orchestration.langgraph.state import TaskStatus, create_initial_state
from tools.mcp.servers.policy_server.tools import search_policy
from tools.mcp.servers.workflow_server.tools import (
    CallerIdentityRequiredError,
    create_case,
)


TEMPLATE = "开办餐馆需要以下手续"


def _policy_state() -> dict:
    state = create_initial_state("我想开一家餐馆需要什么手续")
    state["intent"] = "restaurant_license"
    state["task_plan"] = [
        {"agent": "policy", "type": "search_policy", "status": TaskStatus.PENDING.value},
    ]
    return state


@pytest.mark.asyncio
async def test_workflow_agent_without_client_does_not_invent_case_id():
    agent = WorkflowAgent(allow_stub=False)
    with pytest.raises(WorkflowUnavailable):
        await agent.create_case(user_id="u1", service="restaurant_license")


@pytest.mark.asyncio
async def test_workflow_agent_uses_tool_case_id():
    client = AsyncMock()
    client.call_tool.return_value = {
        "case_id": "CASE_FROMDB",
        "status": "created",
        "service": "restaurant_license",
    }
    agent = WorkflowAgent(mcp_client=client, allow_stub=False)
    result = await agent.create_case(user_id="u1", service="restaurant_license", tenant_id="t1")
    assert result["case_id"] == "CASE_FROMDB"
    assert result.get("mode") != "stub"
    client.call_tool.assert_awaited()


@pytest.mark.asyncio
async def test_workflow_agent_stub_is_labeled():
    agent = WorkflowAgent(allow_stub=True)
    result = await agent.create_case(user_id="u1", service="restaurant_license")
    assert result["mode"] == "stub"
    assert result["status"] == "stub"
    assert str(result["case_id"]).startswith("CASE_")


@pytest.mark.asyncio
async def test_workflow_process_failure_has_empty_case_id():
    agent = WorkflowAgent(allow_stub=False)
    state = create_initial_state("办照", user_id="u1")
    updated = await agent.process(state)
    assert updated["workflow_result"]["status"] == "failed"
    assert updated["workflow_result"]["case_id"] == ""
    assert "CASE_" not in updated["workflow_result"]["error"]


@pytest.mark.asyncio
async def test_policy_node_rejects_stub_documents(monkeypatch):
    monkeypatch.setattr("orchestration.langgraph.nodes._mcp_stub_allowed", lambda: False)
    client = AsyncMock()
    client.call_tool.return_value = {
        "mode": "stub",
        "documents": [{
            "title": "模板",
            "content": TEMPLATE,
            "source": "offline",
            "score": 0.9,
        }],
    }
    state = await policy_node(_policy_state(), mcp_client=client)
    answer = state["policy_result"]["answer"]
    assert TEMPLATE not in answer
    assert state["policy_result"]["mode"] == "unavailable"
    assert state["policy_result"]["evidence"] == []
    assert state["task_plan"][0]["status"] == TaskStatus.FAILED.value


@pytest.mark.asyncio
async def test_policy_node_keeps_retrieved_evidence(monkeypatch):
    monkeypatch.setattr("orchestration.langgraph.nodes._mcp_stub_allowed", lambda: False)
    client = AsyncMock()
    client.call_tool.return_value = {
        "mode": "rag",
        "documents": [{
            "title": "食品经营许可管理办法",
            "content": "申请食品经营许可，应当提交申请书。",
            "source": "《食品经营许可管理办法》第十二条",
            "score": 0.8,
        }],
    }
    state = await policy_node(_policy_state(), mcp_client=client)
    assert state["policy_result"]["mode"] == "retrieval"
    assert state["policy_result"]["evidence"][0]["source"].startswith("《食品经营许可管理办法》")
    assert "申请食品经营许可" in state["policy_result"]["answer"]
    assert state["task_plan"][0]["status"] == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_policy_node_without_client_is_not_a_success(monkeypatch):
    monkeypatch.setattr("orchestration.langgraph.nodes._mcp_stub_allowed", lambda: False)
    state = await policy_node(_policy_state(), mcp_client=None)
    assert TEMPLATE not in state["policy_result"]["answer"]
    assert state["policy_result"]["mode"] == "unavailable"


@pytest.mark.asyncio
async def test_policy_node_explicit_stub_is_labeled(monkeypatch):
    monkeypatch.setattr("orchestration.langgraph.nodes._mcp_stub_allowed", lambda: True)
    state = await policy_node(_policy_state(), mcp_client=None)
    assert state["policy_result"]["mode"] == "stub"
    assert TEMPLATE in state["policy_result"]["answer"]


@pytest.mark.asyncio
async def test_search_policy_rejects_blank_query():
    with pytest.raises(ValueError):
        await search_policy("  ")


@pytest.mark.asyncio
async def test_create_case_requires_caller():
    with pytest.raises(CallerIdentityRequiredError):
        await create_case(user_id="u1", service="restaurant_license", caller=None)


@pytest.mark.asyncio
async def test_create_case_database_failure_is_explicit(monkeypatch):
    async def unavailable(**kwargs):
        return None

    monkeypatch.setattr("database.case_service.create_case", unavailable)
    with pytest.raises(RuntimeError, match="拒绝生成模拟办件"):
        await create_case(
            user_id="u1",
            service="restaurant_license",
            caller={"user_id": "u1", "role": "user", "tenant_id": "t1"},
        )


@pytest.mark.asyncio
async def test_create_case_returns_database_id(monkeypatch):
    async def saved(**kwargs):
        return {
            "case_id": "CASE_DB0001",
            "status": "created",
            "service": kwargs["service"],
            "user_id": kwargs["user_id"],
            "created_at": "2026-09-30T00:00:00+00:00",
        }

    monkeypatch.setattr("database.case_service.create_case", saved)
    result = await create_case(
        user_id="u1",
        service="restaurant_license",
        caller={"user_id": "u1", "role": "user", "tenant_id": "t1"},
    )
    assert result.case_id == "CASE_DB0001"
