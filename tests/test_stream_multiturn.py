"""
SSE 多轮对齐测试（P1-7）。

覆盖 /api/chat/stream 的 conversation_id / prior_messages 透传，
以及 SSE 结束后 user / assistant 消息持久化（与 /api/chat 对齐）。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import routes
from backend.api.dependencies import get_config, get_current_identity, get_trace_id
from backend.config import get_settings


def test_stream_multiturn_persists_messages(monkeypatch):
    """SSE 流式多轮：历史注入 + 结束后持久化 user/assistant 消息。"""
    captured: dict = {}
    calls: list[tuple] = []

    async def fake_stream_agent(
        user_query, user_id, trace_id, settings,
        tenant_id="default", user_role="user",
        conversation_id=None, prior_messages=None,
    ):
        captured["conversation_id"] = conversation_id
        captured["prior_messages"] = prior_messages
        yield ("node", "intent_node")
        yield ("final", {
            "final_answer": "测试回答",
            "intent": "property_service",
            "risk_level": "low",
            "mcp_history": [],
            "evidence": [],
            "error": None,
        })

    monkeypatch.setattr("backend.api.dependencies.stream_agent", fake_stream_agent)

    # conversation_service 函数内懒导入 → patch 模块属性
    conv_states = {"get": 0}

    async def fake_get_conversation(cid):
        conv_states["get"] += 1
        if conv_states["get"] == 1:
            return None  # 多轮加载阶段：会话不存在 → 触发创建
        return {"conversation_id": cid, "title": "新对话", "user_id": "u1"}

    async def fake_create_conversation(user_id, title=None, conversation_id=None):
        calls.append(("create", conversation_id))
        return {"conversation_id": conversation_id}

    async def fake_load_history(cid):
        return [{"role": "user", "content": "历史问题"}, {"role": "assistant", "content": "历史回答"}]

    async def fake_add_message(cid, role, content, trace_id=None):
        calls.append(("add", role, content))

    async def fake_update_conversation_title(cid, title):
        calls.append(("title", title))

    monkeypatch.setattr("backend.services.conversation_service.get_conversation", fake_get_conversation)
    monkeypatch.setattr("backend.services.conversation_service.create_conversation", fake_create_conversation)
    monkeypatch.setattr("backend.services.conversation_service.load_history", fake_load_history)
    monkeypatch.setattr("backend.services.conversation_service.add_message", fake_add_message)
    monkeypatch.setattr("backend.services.conversation_service.update_conversation_title", fake_update_conversation_title)

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[get_current_identity] = lambda: {
        "user_id": "u1", "role": "user", "tenant_id": "default",
    }
    app.dependency_overrides[get_trace_id] = lambda: "trace_x"
    app.dependency_overrides[get_config] = lambda: get_settings()

    client = TestClient(app)
    resp = client.post("/api/chat/stream", json={
        "user_query": "查房产",
        "user_id": "u1",
        "conversation_id": "conv_1",
    })

    assert resp.status_code == 200
    body = resp.text

    # 历史与会话 ID 透传给 stream_agent
    assert captured["conversation_id"] == "conv_1"
    assert captured["prior_messages"] == [
        {"role": "user", "content": "历史问题"},
        {"role": "assistant", "content": "历史回答"},
    ]

    # final 事件带 conversation_id
    assert '"conversation_id": "conv_1"' in body or "conversation_id" in body

    # SSE 结束后持久化 user + assistant 消息
    added = [c for c in calls if c[0] == "add"]
    assert ("add", "user", "查房产") in added
    assert ("add", "assistant", "测试回答") in added
    # 会话创建 + 标题更新
    assert ("create", "conv_1") in calls
    assert ("title", "查房产") in calls
