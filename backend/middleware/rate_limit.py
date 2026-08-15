"""
backend.middleware.rate_limit - per-user/IP request rate limiting middleware

Author: le
Date: 2026/8/14
Version: 0.1
Task: Limit request rate per user/IP to protect LLM and database from overload
"""
from __future__ import annotations

import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import get_settings
from tools.logger import get_logger

logger = get_logger(__name__)


# 公开/基础设施端点不做业务限流（健康检查、指标抓取、接口文档）
_SKIP_PATHS: frozenset[str] = frozenset({
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
})


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI 限流中间件。

    规则:
    - 已认证请求按 user_id 限流；
    - 未认证请求（如开发登录）按客户端 IP 限流；
    - 固定窗口计数，超限返回 429 + Retry-After；
    - 计数在内存中保存，带过期清理，防止长进程内存无限增长。

    注册顺序: 放在 AuthMiddleware 之后执行，以便拿到 request.state.user_id。
    """

    def __init__(self, app=None, **kwargs):
        super().__init__(app, **kwargs)
        self._requests: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._cleanup_counter = 0

    def _client_key(self, request: Request) -> str:
        """生成限流键：优先用户 ID，其次客户端 IP。"""
        user_id = getattr(request.state, "user_id", "")
        if user_id:
            return f"user:{user_id}"
        client = request.client
        ip = client.host if client else "unknown"
        return f"ip:{ip}"

    def _cleanup(self, now: float, window: float) -> None:
        """剔除窗口外记录；条目过多时全量清理一次，防止泄漏。"""
        self._cleanup_counter += 1
        if self._cleanup_counter < 100 and len(self._requests) < 10000:
            return
        expired_keys = [
            key for key, timestamps in self._requests.items()
            if not timestamps or now - timestamps[-1] > window
        ]
        for key in expired_keys:
            self._requests.pop(key, None)
        self._cleanup_counter = 0

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.rate_limit_enabled or request.url.path in _SKIP_PATHS:
            return await call_next(request)

        limit = settings.rate_limit_requests
        window = settings.rate_limit_window_seconds
        key = self._client_key(request)
        now = time.monotonic()

        with self._lock:
            self._cleanup(now, window)
            timestamps = [
                ts for ts in self._requests.get(key, [])
                if now - ts < window
            ]
            if len(timestamps) >= limit:
                retry_after = max(1, int(window - (now - timestamps[0])) + 1)
                logger.warning(
                    "限流触发: key={key}, count={count}, limit={limit}, path={path}",
                    key=key,
                    count=len(timestamps),
                    limit=limit,
                    path=request.url.path,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "RateLimitExceeded",
                        "message": "请求过于频繁，请稍后重试",
                        "retry_after": retry_after,
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )
            timestamps.append(now)
            self._requests[key] = timestamps

        response = await call_next(request)
        with self._lock:
            remaining = max(0, limit - len(self._requests.get(key, [])))
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


# ============================================================
# Smoke Test — python -m backend.middleware.rate_limit
# ============================================================

if __name__ == "__main__":
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    def build_test_app(limit: int = 2, window: int = 60) -> FastAPI:
        app = FastAPI()

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.get("/protected")
        async def protected():
            return {"ok": True}

        app.add_middleware(RateLimitMiddleware)
        return app

    async def main():
        passed = 0
        failed = 0

        def check(description: str, condition: bool, detail: str = ""):
            nonlocal passed, failed
            if condition:
                passed += 1
                print(f"  [PASS] {description}")
            else:
                failed += 1
                print(f"  [FAIL] {description} {detail}")

        print("=== RateLimitMiddleware smoke test ===")
        app = build_test_app()
        with TestClient(app) as client:
            # 绕过限流路径
            resp = client.get("/health")
            check("/health 不受限流影响", resp.status_code == 200)

            # 前两次正常
            r1 = client.get("/protected")
            r2 = client.get("/protected")
            check("第1次请求 200", r1.status_code == 200)
            check("第2次请求 200", r2.status_code == 200)
            check("响应包含 X-RateLimit-Limit", "X-RateLimit-Limit" in r1.headers)

            # 第三次超限
            r3 = client.get("/protected")
            check("第3次请求 429", r3.status_code == 429)
            check("429 包含 Retry-After", "Retry-After" in r3.headers)
            check("429 错误类型", r3.json().get("error") == "RateLimitExceeded")

        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            raise SystemExit(1)
        print(" — all good")
        print("\n  Run with: python -m backend.middleware.rate_limit")

    asyncio.run(main())
