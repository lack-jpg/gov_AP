"""
frontend.api_client - FastAPI 后端 API 客户端（httpx）

作者: le
日期: 2026/8/2
版本: 0.2
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

# 后端 API 地址（FastAPI 服务，默认 8002）
# 容器部署时设置环境变量 API_BASE_URL=http://api:8002
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8002")

# ── Demo Token ──
# 开发/演示用 JWT Token（避免硬编码 X-User-Id / X-User-Role Header）。
# 生产环境应使用真实的用户登录流程获取 Token。
_DEMO_TOKEN: str | None = None


def _get_demo_token() -> str:
    """获取或创建演示用 JWT Token"""
    global _DEMO_TOKEN
    if _DEMO_TOKEN is not None:
        return _DEMO_TOKEN
    try:
        from backend.middleware.auth import create_access_token
        _DEMO_TOKEN = create_access_token(user_id="demo_user", role="user")
    except Exception:
        # 无法导入或创建 JWT Token 时（如 Docker 前端、配置缺失），回退生成简单 Token
        import hashlib
        import time
        payload = f"demo_user:{int(time.time())}"
        _DEMO_TOKEN = f"demo_{hashlib.sha256(payload.encode()).hexdigest()[:32]}"
    return _DEMO_TOKEN


def _headers() -> dict[str, str]:
    """构建认证请求头（Bearer Token + X-User-Id 双重兜底）。

    Docker 前端容器无法导入 backend.middleware.auth，会生成非 JWT 的假 Token。
    后端 AuthMiddleware 的 JWT 校验失败后会 fallthrough 到 X-User-Id 降级路径。
    """
    return {
        "Authorization": f"Bearer {_get_demo_token()}",
        "X-User-Id": "demo_user",
        "X-User-Role": "user",
    }


def _get(path: str, params: Optional[dict] = None, timeout: float = 10.0) -> Optional[dict]:
    """GET 请求（错误时返回 None）"""
    try:
        r = httpx.get(
            f"{BASE_URL}{path}",
            params=params,
            headers=_headers(),
            timeout=timeout,
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def health() -> Optional[dict]:
    """后端健康检查"""
    return _get("/health", timeout=3)


def chat(user_query: str, user_id: str = "demo_user") -> tuple[int, dict]:
    """
    多 Agent 对话（POST /api/chat）。

    Returns:
        (status_code, response_dict)
    """
    try:
        r = httpx.post(
            f"{BASE_URL}/api/chat",
            json={"user_query": user_query, "user_id": user_id},
            headers=_headers(),
            timeout=180,  # 真实 LLM + MCP 调用可能较慢
        )
        if r.status_code == 200:
            return 200, r.json()
        return r.status_code, {"error": r.text[:300]}
    except Exception as e:
        return 0, {"error": str(e)}


def chat_with_fallback(user_query: str, user_id: str = "demo_user") -> tuple[int, dict]:
    """
    多 Agent 对话（自动降级：API → 本地 stub）。

    优先调用后端 /api/chat；后端不可用时自动降级为本地 stub 模式，
    使用本地 BERT 意图分类 + stub 政策模板，保证演示可用。

    Returns:
        (status_code, response_dict)
        - 200: 后端正常响应 或 stub 降级成功（response 含 mode="stub"）
        - 0:  后端不可用且 stub 也失败
    """
    # 1. 尝试后端 API
    if health():
        return chat(user_query, user_id)

    # 2. 降级：本地 stub 模式
    try:
        import asyncio
        from stub_chat import run_stub_chat

        result = asyncio.run(run_stub_chat(user_query, user_id))
        return 200, result
    except ImportError as e:
        return 0, {"error": f"后端不可用，本地 stub 模块加载失败: {e}"}
    except Exception as e:
        return 0, {"error": f"后端不可用，本地 stub 执行失败: {e}"}


def dashboard_overview() -> Optional[dict]:
    """运维看板概览（GET /api/dashboard/overview）"""
    return _get("/api/dashboard/overview")


def agent_status(trace_id: str) -> Optional[dict]:
    """Agent 执行状态（GET /api/agent/status/{trace_id}）"""
    return _get(f"/api/agent/status/{trace_id}")


def evaluation_report(version: str = "v1") -> Optional[dict]:
    """评测报告（GET /api/evaluation/report/{version}）"""
    return _get(f"/api/evaluation/report/{version}")
