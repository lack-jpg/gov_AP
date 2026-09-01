"""
API 路由层集成测试（P4-2）。

轻量 FastAPI app（仅挂载 /api 路由 + 依赖覆盖），不加载认证/RBAC 中间件
（中间件行为由 test_api_auth.py 覆盖）。聚焦路由业务逻辑与数据归属校验：
- /api/chat 主链路与跨用户会话越权（P0-4 数据隔离）
- /api/conversations 创建 / 列表 / 消息归属
- /api/dashboard/overview 概览
- /api/evaluation/report/{version} DB 不可用回退文件
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import routes
from backend.api.dependencies import (
    get_config,
    get_current_identity,
    get_trace_id,
    get_user_id,
)
from backend.config import get_settings


def _make_client(user_id: str = "u1", role: str = "user", tenant_id: str = "default") -> TestClient:
    """构造轻量测试 app：挂载 /api 路由并覆盖身份/配置依赖。"""
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[get_current_identity] = lambda: {
        "user_id": user_id,
        "role": role,
        "tenant_id": tenant_id,
    }
    app.dependency_overrides[get_user_id] = lambda: user_id
    app.dependency_overrides[get_trace_id] = lambda: "trace_x"
    app.dependency_overrides[get_config] = lambda: get_settings()
    return TestClient(app)


# ── /api/chat 主链路 ──


def test_chat_main_chain(monkeypatch):
    """chat 端点正确透传用户身份并返回结构化结果。"""
    captured: dict = {}

    async def fake_execute_agent(**kwargs):
        captured.update(
            {
                "user_id": kwargs["user_id"],
                "trace_id": kwargs["trace_id"],
                "user_query": kwargs["user_query"],
                "user_role": kwargs["user_role"],
            }
        )
        return {
            "final_answer": "需要办理营业执照",
            "intent": "business_license",
            "risk_level": "low",
            "evidence": [{"source": "工商条例", "excerpt": "应当办理", "relevance_score": 0.9}],
            "mcp_history": [{"tool": "search_policy"}],
            "error": None,
        }

    monkeypatch.setattr("backend.api.routes.execute_agent", fake_execute_agent)
    client = _make_client()
    resp = client.post("/api/chat", json={"user_query": "开餐馆", "user_id": "u1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "需要办理营业执照"
    assert data["intent"] == "business_license"
    assert data["risk_level"] == "low"
    assert data["execution_steps"] == 1
    assert data["evidence"][0]["source"] == "工商条例"
    # 身份与查询正确透传
    assert captured["user_id"] == "u1"
    assert captured["user_query"] == "开餐馆"
    assert captured["user_role"] == "user"


def test_chat_foreign_conversation_404(monkeypatch):
    """A 用户携带 B 用户的会话 ID 请求 → 404（P0-4 数据隔离）。"""
    async def fake_get_conversation(cid, **kwargs):
        return {"conversation_id": cid, "user_id": "another_user", "title": "x"}

    monkeypatch.setattr(
        "backend.services.conversation_service.get_conversation", fake_get_conversation,
    )
    client = _make_client(user_id="u1")
    resp = client.post(
        "/api/chat",
        json={"user_query": "查政策", "user_id": "u1", "conversation_id": "conv_other"},
    )
    assert resp.status_code == 404


# ── /api/conversations ──


def test_create_conversation(monkeypatch):
    async def fake_create(user_id, title=None, conversation_id=None):
        return {"conversation_id": "conv_new", "user_id": user_id}

    monkeypatch.setattr(
        "backend.services.conversation_service.create_conversation", fake_create,
    )
    client = _make_client(user_id="u1")
    resp = client.post("/api/conversations")
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == "conv_new"


def test_list_conversations(monkeypatch):
    async def fake_list(user_id, **kwargs):
        return [{"conversation_id": "c1", "user_id": user_id}]

    monkeypatch.setattr(
        "backend.services.conversation_service.list_conversations", fake_list,
    )
    client = _make_client(user_id="u1")
    resp = client.get("/api/conversations")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["conversation_id"] == "c1"


def test_conversation_messages_ownership_404(monkeypatch):
    """会话不存在或不属于当前用户 → 404。"""
    async def fake_get_conversation(cid, **kwargs):
        return None

    monkeypatch.setattr(
        "backend.services.conversation_service.get_conversation", fake_get_conversation,
    )
    client = _make_client(user_id="u1")
    resp = client.get("/api/conversations/conv_x/messages")
    assert resp.status_code == 404


def test_conversation_messages_ok(monkeypatch):
    async def fake_get_conversation(cid, **kwargs):
        return {"conversation_id": cid, "user_id": "u1", "title": "x"}

    async def fake_list_messages(cid, **kwargs):
        return [{"role": "user", "content": "你好", "trace_id": "", "created_at": ""}]

    monkeypatch.setattr(
        "backend.services.conversation_service.get_conversation", fake_get_conversation,
    )
    monkeypatch.setattr(
        "backend.services.conversation_service.list_messages", fake_list_messages,
    )
    client = _make_client(user_id="u1")
    resp = client.get("/api/conversations/conv_1/messages")
    assert resp.status_code == 200
    assert resp.json()["messages"][0]["role"] == "user"


# ── /api/dashboard/overview ──


def test_dashboard_overview_empty(monkeypatch):
    """无数据时返回空指标结构。"""
    class FakeSummary:
        agent_stats = []
        eval_trends = []

    class FakeProvider:
        async def get_summary(self, use_db=True):
            return FakeSummary()

    monkeypatch.setattr("governance.dashboard.get_dashboard_provider", lambda: FakeProvider())
    client = _make_client()
    resp = client.get("/api/dashboard/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_requests"] == 0
    assert data["success_rate"] == 0.0
    assert "active_agents" in data
    assert "eval_trends" in data


# ── /api/evaluation/report/{version} ──


def test_evaluation_report_file_fallback(monkeypatch):
    """DB 不可用时回退 evaluation_results 文件（PLAN 评测读取策略）。"""
    fake_report = {
        "version": "v_test",
        "task_success_rate": 0.9,
        "rag_faithfulness": 0.8,
        "rag_answer_relevance": 0.7,
        "rag_context_recall": 0.6,
        "tool_accuracy": 0.9,
        "avg_latency_ms": 120.0,
        "avg_step_count": 5.0,
        "total_cases": 10,
        "passed_cases": 9,
        "source": "file",
    }

    # DB 不可用：get_session_factory 返回 None → 函数内 `async with None() as session` 抛错 → 走文件回退
    monkeypatch.setattr("database.connection.get_session_factory", lambda: None)
    monkeypatch.setattr("backend.api.routes._load_benchmark_report_file", lambda v: fake_report)
    client = _make_client()
    resp = client.get("/api/evaluation/report/v_test")

    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "v_test"
    assert data["source"] == "file"
    assert data["task_success_rate"] == 0.9
    assert data["total_cases"] == 10
