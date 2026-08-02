"""
frontend.api_client - FastAPI 后端 API 客户端（httpx）

作者: le
日期: 2026/8/2
版本: 0.1
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

# 后端 API 地址（FastAPI 服务，默认 8002）
BASE_URL = "http://localhost:8002"


def _get(path: str, params: Optional[dict] = None, timeout: float = 10.0) -> Optional[dict]:
    """GET 请求（错误时返回 None）"""
    try:
        r = httpx.get(
            f"{BASE_URL}{path}",
            params=params,
            headers={"X-User-Id": "admin", "X-User-Role": "admin"},
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
            headers={"X-User-Id": user_id},
            timeout=180,  # 真实 LLM + MCP 调用可能较慢
        )
        if r.status_code == 200:
            return 200, r.json()
        return r.status_code, {"error": r.text[:300]}
    except Exception as e:
        return 0, {"error": str(e)}


def dashboard_overview() -> Optional[dict]:
    """运维看板概览（GET /api/dashboard/overview）"""
    return _get("/api/dashboard/overview")


def agent_status(trace_id: str) -> Optional[dict]:
    """Agent 执行状态（GET /api/agent/status/{trace_id}）"""
    return _get(f"/api/agent/status/{trace_id}")


def evaluation_report(version: str = "v1") -> Optional[dict]:
    """评测报告（GET /api/evaluation/report/{version}）"""
    return _get(f"/api/evaluation/report/{version}")
