"""
API 认证与 RBAC 集成测试（P4-2）。

使用完整应用（create_app + 全部中间件）验证身份与权限边界：
- JWT 缺失 / 无效 / 伪造 Header → 401（P0-1 防身份伪造）
- 角色权限：guest 访问 /api/chat → 403；prompts 写操作仅 admin 可执行
- 有效 user token 通过认证与 RBAC，正常进入业务逻辑
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.middleware.auth import create_access_token


@pytest.fixture
def client() -> TestClient:
    """完整应用实例（直接实例化不触发 lifespan，避免 DB 依赖）。"""
    return TestClient(create_app())


# ── 认证边界：缺失 / 无效 / 伪造 → 401 ──


def test_chat_requires_bearer_token(client):
    """无 Authorization 头 → 401。"""
    resp = client.post("/api/chat", json={"user_query": "你好", "user_id": "u1"})
    assert resp.status_code == 401


def test_chat_rejects_invalid_token(client):
    """无效 JWT → 401。"""
    resp = client.post(
        "/api/chat",
        json={"user_query": "你好", "user_id": "u1"},
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


def test_chat_rejects_forged_x_user_id(client):
    """X-User-Id / X-User-Role Header 不再是身份来源（P0-1 防身份伪造）。"""
    resp = client.post(
        "/api/chat",
        json={"user_query": "你好", "user_id": "admin"},
        headers={"X-User-Id": "admin", "X-User-Role": "admin"},
    )
    assert resp.status_code == 401


def test_prompts_read_requires_auth(client):
    """Prompt 管理读接口也要求登录。"""
    resp = client.get("/api/prompts")
    assert resp.status_code == 401


# ── RBAC：角色权限 ──


def test_guest_cannot_chat(client):
    """guest 角色无权调用 /api/chat（RBAC 拦截在业务执行前）。"""
    token = create_access_token(user_id="guest1", role="guest")
    resp = client.post(
        "/api/chat",
        json={"user_query": "你好", "user_id": "guest1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_prompts_write_requires_admin(client):
    """user 角色写 Prompt 模板 → 403。"""
    user_token = create_access_token(user_id="u1", role="user")
    resp = client.post(
        "/api/prompts",
        json={
            "name": "TEST_PROMPT",
            "agent_name": "supervisor",
            "version": "v1",
            "content": "hello",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


def test_prompts_write_allowed_for_admin(client):
    """admin 角色写 Prompt 模板 → 201。用唯一模板名避免污染其他用例。"""
    from prompts.registry import get_registry

    name = f"ITEST_{uuid.uuid4().hex[:8]}"
    admin_token = create_access_token(user_id="admin1", role="admin")
    resp = client.post(
        "/api/prompts",
        json={
            "name": name,
            "agent_name": "supervisor",
            "version": "v_it",
            "content": "你是政务助手",
            "variables": ["user_query"],
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["success"] is True
    # 清理残留（test_prompts 各用例 setup 时会 reset_registry，此处兜底）
    assert get_registry().get(name) is not None


def test_chat_with_valid_user_token(monkeypatch, client):
    """有效 user token 通过认证与 RBAC，进入业务逻辑。"""
    async def fake_execute_agent(**kwargs):
        return {
            "final_answer": "需要办理材料",
            "intent": "business_license",
            "risk_level": "low",
            "evidence": [],
            "mcp_history": [],
            "error": None,
        }

    monkeypatch.setattr("backend.api.routes.execute_agent", fake_execute_agent)
    token = create_access_token(user_id="u1", role="user")
    resp = client.post(
        "/api/chat",
        json={"user_query": "开餐馆", "user_id": "u1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["answer"] == "需要办理材料"
