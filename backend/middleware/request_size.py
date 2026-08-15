"""
backend.middleware.request_size - global request body size limit middleware

Author: le
Date: 2026/8/14
Version: 0.1
Task: Reject oversized request bodies (uploads, OCR payloads) with 413
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import get_settings
from tools.logger import get_logger

logger = get_logger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI 请求体大小限制中间件。

    依据 Content-Length 拒绝超大请求体，避免将超大载荷送入 LLM / 数据库。
    注册为最外层中间件，在任何业务处理前生效。
    """

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                length = int(content_length)
            except ValueError:
                length = 0
            if length > settings.max_request_body_bytes:
                logger.warning(
                    "请求体超限: path={path}, size={size}, max={max}",
                    path=request.url.path,
                    size=length,
                    max=settings.max_request_body_bytes,
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "PayloadTooLarge",
                        "message": (
                            "请求体过大，超出系统限制 "
                            f"({settings.max_request_body_bytes} bytes)"
                        ),
                    },
                )
        return await call_next(request)


# ============================================================
# Smoke Test — python -m backend.middleware.request_size
# ============================================================

if __name__ == "__main__":
    import asyncio

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    def build_test_app() -> FastAPI:
        app = FastAPI()

        @app.post("/echo")
        async def echo():
            return {"ok": True}

        app.add_middleware(RequestSizeLimitMiddleware)
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

        print("=== RequestSizeLimitMiddleware smoke test ===")
        app = build_test_app()
        with TestClient(app) as client:
            # 小请求正常
            resp = client.post("/echo", json={"data": "small"})
            check("小请求 200", resp.status_code == 200)

            # 超大 Content-Length 拒绝
            oversized = "x" * (2 * 1024 * 1024 + 1)
            resp2 = client.post(
                "/echo",
                content=oversized,
                headers={"Content-Type": "text/plain"},
            )
            check("超大请求 413", resp2.status_code == 413)
            check("413 错误类型", resp2.json().get("error") == "PayloadTooLarge")

        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            raise SystemExit(1)
        print(" — all good")
        print("\n  Run with: python -m backend.middleware.request_size")

    asyncio.run(main())
