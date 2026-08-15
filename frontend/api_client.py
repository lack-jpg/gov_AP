"""
frontend.api_client - FastAPI 后端 API 客户端（httpx）

作者: le
日期: 2026/8/2
版本: 0.2
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

# 后端 API 地址（FastAPI 服务，默认 12401）
# 容器部署时设置环境变量 API_BASE_URL=http://api:12401
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:12401")

# ── 认证 Token ──
# 前端不再自行构造假 Token / X-User-Id Header。
# Token 来源（按优先级）:
#   1. FRONTEND_AUTH_TOKEN — 运维注入的真实 JWT（生产推荐）
#   2. FRONTEND_DEV_AUTH=1 — 开发模式，向后端 /api/auth/dev-login 换取 Token
# 两者均未配置时，请求直接失败并给出明确提示，避免静默降级。
_TOKEN: str | None = None


def set_token(token: str) -> None:
    """注入认证 Token（登录成功后调用，写入模块级缓存）。"""
    global _TOKEN
    _TOKEN = token


def logout() -> None:
    """清除本地认证 Token。"""
    global _TOKEN
    _TOKEN = None


def login(username: str, password: str) -> tuple[int, dict]:
    """
    用户登录（POST /api/auth/login）。

    Returns:
        (status_code, data)
        - 200: data 含 access_token / user_id / role / tenant_id
        - 401: data 含 error（用户名或密码错误）
        - 0:   后端不可达
    """
    try:
        r = httpx.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            set_token(data.get("access_token", ""))
            return 200, data
        return r.status_code, {"error": r.text[:300]}
    except Exception as e:
        return 0, {"error": str(e)}


def _get_token() -> str:
    """获取认证 Token（环境注入或开发登录接口换取）。"""
    global _TOKEN
    if _TOKEN:
        return _TOKEN

    injected = os.getenv("FRONTEND_AUTH_TOKEN", "").strip()
    if injected:
        _TOKEN = injected
        return _TOKEN

    dev_auth = os.getenv("FRONTEND_DEV_AUTH", "").strip().lower()
    if dev_auth in ("1", "true", "yes"):
        try:
            r = httpx.post(
                f"{BASE_URL}/api/auth/dev-login",
                timeout=10,
            )
            if r.status_code != 200:
                raise RuntimeError(f"开发登录失败: HTTP {r.status_code}")
            token = (r.json() or {}).get("access_token", "")
            if not token:
                raise RuntimeError("开发登录响应缺少 access_token")
            _TOKEN = token
            return _TOKEN
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"开发登录请求失败: {e}") from e

    raise RuntimeError(
        "未配置认证 Token：请设置 FRONTEND_AUTH_TOKEN，"
        "或开发环境设置 FRONTEND_DEV_AUTH=1 启用 /api/auth/dev-login"
    )


def _headers() -> dict[str, str]:
    """构建认证请求头（仅 Bearer Token，无 Header 身份兜底）。"""
    return {"Authorization": f"Bearer {_get_token()}"}


def _get(
    path: str,
    params: Optional[dict] = None,
    timeout: float = 10.0,
    auth: bool = True,
) -> Optional[dict]:
    """GET 请求（错误时返回 None）"""
    try:
        r = httpx.get(
            f"{BASE_URL}{path}",
            params=params,
            headers=_headers() if auth else {},
            timeout=timeout,
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def health() -> Optional[dict]:
    """后端健康检查"""
    return _get("/health", timeout=3, auth=False)


def chat(
    user_query: str,
    user_id: str = "demo_user",
    conversation_id: Optional[str] = None,
) -> tuple[int, dict]:
    """
    多 Agent 对话（POST /api/chat）。

    Args:
        user_query: 用户输入
        user_id: 用户 ID
        conversation_id: 会话 ID（多轮对话时携带，后端据此保留上下文）

    Returns:
        (status_code, response_dict)
    """
    body: dict[str, Any] = {"user_query": user_query, "user_id": user_id}
    if conversation_id:
        body["conversation_id"] = conversation_id
    try:
        r = httpx.post(
            f"{BASE_URL}/api/chat",
            json=body,
            headers=_headers(),
            timeout=180,  # 真实 LLM + MCP 调用可能较慢
        )
        if r.status_code == 200:
            return 200, r.json()
        return r.status_code, {"error": r.text[:300]}
    except Exception as e:
        return 0, {"error": str(e)}


def chat_stream(
    user_query: str,
    user_id: str = "demo_user",
    conversation_id: Optional[str] = None,
):
    """
    流式对话（POST /api/chat/stream，SSE）。

    yield 事件 dict:
        {"event": "node", "node": "...", "label": "..."}   # 节点进度
        {"event": "final", "answer": "...", "trace_id": "...", ...}
        {"event": "error", "message": "..."}
    """
    body: dict[str, Any] = {"user_query": user_query, "user_id": user_id}
    if conversation_id:
        body["conversation_id"] = conversation_id
    try:
        with httpx.Client(timeout=180) as client:
            with client.stream(
                "POST",
                f"{BASE_URL}/api/chat/stream",
                json=body,
                headers=_headers(),
            ) as resp:
                if resp.status_code != 200:
                    yield {"event": "error", "message": f"HTTP {resp.status_code}"}
                    return
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    try:
                        yield json.loads(data)
                    except ValueError:
                        continue
    except Exception as e:
        yield {"event": "error", "message": str(e)}


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


def create_conversation(user_id: str = "demo_user") -> Optional[dict]:
    """创建多轮对话会话（POST /api/conversations）"""
    try:
        r = httpx.post(
            f"{BASE_URL}/api/conversations",
            headers=_headers(),
            timeout=10,
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def list_conversations(user_id: str = "demo_user") -> dict:
    """会话列表（GET /api/conversations）"""
    return _get("/api/conversations") or {"items": [], "total": 0}


def get_conversation_messages(conversation_id: str) -> dict:
    """会话消息（GET /api/conversations/{id}/messages）"""
    return _get(f"/api/conversations/{conversation_id}/messages") or {"messages": []}


def dashboard_overview() -> Optional[dict]:
    """运维看板概览（GET /api/dashboard/overview）"""
    return _get("/api/dashboard/overview")


def agent_status(trace_id: str) -> Optional[dict]:
    """Agent 执行状态（GET /api/agent/status/{trace_id}）"""
    return _get(f"/api/agent/status/{trace_id}")


def evaluation_report(version: str = "v1") -> Optional[dict]:
    """评测报告（GET /api/evaluation/report/{version}）"""
    return _get(f"/api/evaluation/report/{version}")
