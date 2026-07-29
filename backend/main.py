"""
backend.main - FastAPI application entry point: app creation, middleware registration, router mounting

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement FastAPI app factory with CORS, middleware, and route registration
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.middleware.logging import (
    RequestLoggingMiddleware,
    setup_logging,
    get_logger,
    get_current_trace_id,
    get_current_user_id,
    get_current_agent_name,
)

# ============================================================
# Lifespan — 应用启动/关闭事件
# ============================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan事件处理器。

    Startup:
        - 初始化 loguru 日志系统
        - 初始化数据库连接池（TODO）
        - 预热Agent Graph（TODO）

    Shutdown:
        - 关闭数据库连接池（TODO）
        - 关闭Redis连接（TODO）
    """
    settings = get_settings()

    # ── Startup ──
    setup_logging(settings)

    logger = get_logger(__name__)
    logger.info(
        f"启动 {settings.app_name} v{settings.app_version} (debug={settings.debug})"
    )
    logger.info(f"LLM: {settings.llm_api_url} model={settings.llm_model}")
    logger.info(
        f"PostgreSQL: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    logger.info(f"Redis: {settings.redis_host}:{settings.redis_port}")
    logger.info(f"MCP Gateway: {settings.mcp_gateway_url}")

    # 创建日志目录
    import os
    os.makedirs("logs", exist_ok=True)

    yield  # App运行中

    # ── Shutdown ──
    logger.info("正在关闭应用...")


# ============================================================
# App Factory
# ============================================================


def create_app() -> FastAPI:
    """
    创建并配置FastAPI应用。

    Returns:
        配置好的FastAPI实例
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="政务多智能体协同与治理平台 — LangGraph + MCP + A2A + AgentOps + RAG",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 请求日志中间件（trace_id注入 + 请求/响应日志） ──
    app.add_middleware(RequestLoggingMiddleware)

    # ── 全局异常处理 ──
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """
        全局异常处理器。

        不泄露内部异常详情（traceback仅记录到日志文件）。
        返回统一的错误响应格式。
        """
        logger = get_logger("backend.exception_handler")
        trace_id = get_current_trace_id() or getattr(
            getattr(request, "state", None), "trace_id", "unknown"
        )

        logger.error(f"[{trace_id}] 未处理的异常: {type(exc).__name__}: {exc}")
        logger.opt(exception=True).debug("异常详情:")

        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "message": "服务器内部错误，请稍后重试",
                "trace_id": trace_id,
            },
        )

    # ── 注册路由 ──
    from backend.api.routes import router as api_router
    app.include_router(api_router, prefix="/api")

    # ── 健康检查 ──
    @app.get("/health")
    async def health_check():
        """健康检查端点"""
        return {
            "status": "healthy",
            "app": settings.app_name,
            "version": settings.app_version,
            "log_level": settings.log_level,
        }

    logger = get_logger(__name__)
    logger.info(f"FastAPI app构建完成: {settings.app_name} v{settings.app_version}")
    return app


# ============================================================
# 模块级app实例（uvicorn入口: backend.main:app）
# ============================================================

app = create_app()
