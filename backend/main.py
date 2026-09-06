"""
backend.main - FastAPI application entry point: app creation, middleware registration, router mounting

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement FastAPI app factory with CORS, middleware, and route registration
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from tools.logger import (
    RequestLoggingMiddleware,
    setup_logging,
    get_logger,
    get_current_trace_id,
)


# ============================================================
# Lifespan — 应用启动/关闭事件
# ============================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan事件处理器。

    Startup:
        1. 初始化日志系统
        2. 初始化数据库连接池 + 建表
        3. 预热 Agent Graph（TODO）

    Shutdown:
        1. 关闭数据库连接池
        2. 关闭 Redis 连接（TODO）
    """
    settings = get_settings()

    # ── Startup ──
    setup_logging(settings, serialize=settings.log_serialize)

    logger = get_logger(__name__)
    logger.info("启动 {} v{} (debug={})", settings.app_name, settings.app_version, settings.debug)
    logger.info("LLM: {} model={}", settings.llm_api_url, settings.llm_model)
    logger.info("PostgreSQL: {}:{}/{}", settings.postgres_host, settings.postgres_port, settings.postgres_db)
    logger.info("Redis: {}:{}", settings.redis_host, settings.redis_port)
    logger.info("MCP Gateway: {}", settings.mcp_gateway_url)

    # ── P2-6 OpenTelemetry 初始化（SDK 缺失时内部自动降级 NoOp）──
    tracing_manager = None
    try:
        from backend.middleware.tracing import setup_tracing
        tracing_manager = await setup_tracing(
            service_name="gov-agent-platform",
            endpoint=settings.otel_exporter_endpoint,
        )
    except Exception as e:
        logger.warning("OpenTelemetry 初始化失败，降级 NoOp: {}", e)

    # ── P2-6 LangSmith 自动追踪：config 用 LANGSMITH_*，langsmith 自动追踪读 LANGCHAIN_* ──
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

    # 初始化数据库（PostgreSQL）
    try:
        from database.connection import init_db
        await init_db()
        logger.info("PostgreSQL 初始化完成")
    except Exception as e:
        logger.warning("PostgreSQL 初始化失败（将以无DB模式运行）: {}", e)

    # ── P2-4 Prompt Registry：启动时从 DB 加载，空表时写入默认版本 ──
    try:
        from prompts.registry import get_registry
        _prompt_registry = get_registry()
        _loaded = await _prompt_registry.load_from_db()
        if _loaded == 0:
            _loaded = await _prompt_registry.flush_to_db()
        logger.info("Prompt Registry 就绪（DB 加载 {} 条）", _loaded)
    except Exception as e:
        logger.warning("Prompt Registry 初始化失败，使用内置默认模板: {}", e)

    # 初始化默认管理员账号（User 表为空时创建）
    try:
        from database.auth_service import seed_default_admin
        await seed_default_admin()
    except Exception as e:
        logger.warning("默认管理员账号初始化失败: {}", e)

    # 恢复 A2A 任务存储（重启后回调仍能定位原任务）
    try:
        from tools.a2a.task import get_task_store

        store = get_task_store()
        if hasattr(store, "hydrate"):
            await store.hydrate()
    except Exception as e:
        logger.warning("A2A 任务存储恢复失败: {}", e)

    # 初始化 Redis
    try:
        from database.redis import init_redis
        await init_redis()
        logger.info("Redis 初始化完成")
    except Exception as e:
        logger.warning("Redis 初始化失败（将以无缓存模式运行）: {}", e)

    yield  # App运行中

    # ── Shutdown ──
    logger.info("正在关闭应用...")
    if tracing_manager is not None:
        try:
            await tracing_manager.shutdown()
        except Exception:
            pass
    try:
        from database.connection import close_db
        await close_db()
        logger.info("PostgreSQL 连接池已关闭")
    except Exception:
        pass
    try:
        from database.redis import close_redis
        await close_redis()
        logger.info("Redis 连接已关闭")
    except Exception:
        pass


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

    # 安全基线校验：非 debug 环境缺失强 JWT 密钥时拒绝启动
    from backend.config import validate_security_config
    validate_security_config(settings)

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

    # ── 链路追踪中间件（OpenTelemetry trace/span 注入） ──
    try:
        from backend.middleware.tracing import TracingMiddleware
        app.add_middleware(TracingMiddleware)
    except Exception:
        pass

    # ── 权限中间件（RBAC 角色/权限校验 — 依赖 AuthMiddleware 注入的 user_role） ──
    try:
        from backend.middleware.rbac import RBACMiddleware
        app.add_middleware(RBACMiddleware)  # type: ignore[arg-type]  # Starlette stub 将中间件类收窄为 factory
    except Exception:
        pass

    # ── 限流中间件（按用户 ID/IP 限流，在 Auth 之后执行以获取用户身份） ──
    try:
        from backend.middleware.rate_limit import RateLimitMiddleware
        app.add_middleware(RateLimitMiddleware)  # type: ignore[arg-type]  # Starlette stub 将中间件类收窄为 factory
    except Exception:
        pass

    # ── 认证中间件（JWT Bearer Token → request.state 注入 — 必须在 RBAC 之前执行） ──
    try:
        from backend.middleware.auth import AuthMiddleware
        app.add_middleware(AuthMiddleware)  # type: ignore[arg-type]  # Starlette stub 将中间件类收窄为 factory
    except Exception:
        pass

    # ── 请求日志中间件（trace_id注入 + 请求/响应日志） ──
    app.add_middleware(RequestLoggingMiddleware)

    # ── 请求体大小限制中间件（最外层，任何业务处理前生效） ──
    try:
        from backend.middleware.request_size import RequestSizeLimitMiddleware
        app.add_middleware(RequestSizeLimitMiddleware)
    except Exception:
        pass

    # ── 全局异常处理（不拦截 HTTPException — 由 Starlette 原样返回） ──
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """
        全局异常处理器。

        仅处理真正的未预期异常（非 HTTPException），避免泄露内部错误详情。
        HTTPException（401/403/404 等）由 Starlette 原样返回给客户端。
        """
        # HTTPException 是 Starlette 有意抛出的，不应被全局 handler 屏蔽
        from starlette.exceptions import HTTPException as StarletteHTTPException
        if isinstance(exc, StarletteHTTPException):
            raise exc

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

    # ── P2-4 Prompt 管理 API（/api/prompts*） ──
    try:
        from backend.api.prompts import router as prompts_router
        app.include_router(prompts_router, prefix="/api")
    except Exception as e:
        get_logger(__name__).warning("Prompt 管理 API 注册失败: {}", e)

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

    # ── Prometheus 指标（供 Prometheus 抓取，无需认证） ──
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        """返回 Prometheus 文本格式的运行指标（取自 MetricsCollector）。"""
        from fastapi.responses import PlainTextResponse
        from governance.monitor import export_prometheus_metrics

        return PlainTextResponse(
            export_prometheus_metrics(),
            media_type="text/plain; version=0.0.4",
        )

    logger = get_logger(__name__)
    logger.info(f"FastAPI app构建完成: {settings.app_name} v{settings.app_version}")
    return app


# ============================================================
# 模块级app实例（uvicorn入口: backend.main:app）
# ============================================================

app = create_app()
