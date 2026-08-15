"""
tests/test_auth_login.py — 登录功能测试（用户名密码 → JWT）

验证：
1. bcrypt 密码哈希不存明文、校验正确；
2. POST /api/auth/login：正确密码签发 JWT、错误密码/未知用户返回 401。
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from database.auth_service import hash_password, verify_password


def test_hash_and_verify_password():
    """bcrypt 哈希不存明文，正确/错误密码校验结果正确。"""
    h = hash_password("admin123")
    assert h != "admin123"
    assert h.startswith("$2")
    assert verify_password("admin123", h) is True
    assert verify_password("wrong", h) is False


def test_verify_password_bad_hash():
    """哈希损坏时安全返回 False 而非抛异常。"""
    assert verify_password("x", "not-a-valid-hash") is False


async def test_login_ok(monkeypatch):
    """正确密码 → 签发 JWT，身份取自 user 表角色。"""
    from backend.api.routes import login
    from backend.api.schemas import LoginRequest

    h = hash_password("admin123")

    class FakeUser:
        username = "admin"
        role = "admin"
        tenant_id = "default"
        password_hash = h

    async def fake_get_user(_username: str):
        assert _username == "admin"
        return FakeUser()

    monkeypatch.setattr("database.auth_service.get_user_by_username", fake_get_user)

    resp = await login(LoginRequest(username="admin", password="admin123"))
    assert resp.access_token
    assert resp.token_type == "bearer"
    assert resp.user_id == "admin"
    assert resp.role == "admin"


async def test_login_wrong_password(monkeypatch):
    """错误密码 → 401。"""
    from backend.api.routes import login
    from backend.api.schemas import LoginRequest

    class FakeUser:
        username = "admin"
        role = "admin"
        tenant_id = "default"
        password_hash = hash_password("admin123")

    async def fake_get_user(_username: str):
        return FakeUser()

    monkeypatch.setattr("database.auth_service.get_user_by_username", fake_get_user)

    with pytest.raises(HTTPException) as exc:
        await login(LoginRequest(username="admin", password="wrong"))
    assert exc.value.status_code == 401


async def test_login_unknown_user(monkeypatch):
    """用户不存在 → 401。"""
    from backend.api.routes import login
    from backend.api.schemas import LoginRequest

    async def fake_get_user(_username: str):
        return None

    monkeypatch.setattr("database.auth_service.get_user_by_username", fake_get_user)

    with pytest.raises(HTTPException) as exc:
        await login(LoginRequest(username="nobody", password="x"))
    assert exc.value.status_code == 401
