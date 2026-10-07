"""
backend.main - FastAPI application entry point: app creation, middleware registration, router mounting

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement FastAPI app factory with CORS, middleware, and route registration
"""
from __future__ import annotations

import importlib
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
# 中间件注册 — 安全中间件不允许静默失效
# ============================================================

# (显示名, 模块路径, 类名, 是否安全关键)
#
# 顺序即 app.add_middleware 的注册顺序，不可调整：
# Starlette 后注册的中间件位于更外层，当前顺序的实际执行链为
#   request_size → request_logging → auth → rate_limit → rbac → tracing
_MIDDLEWARE_SPEC: list[tuple[str, str | None, str, bool]] = [
    ("tracing", "backend.middleware.tracing", "TracingMiddleware", False),
    ("rbac", "backend.middleware.rbac", "RBACMiddleware", True),
    ("rate_limit", "backend.middleware.rate_limit", "RateLimitMiddleware", True),
    ("auth", "backend.middleware.auth", "AuthMiddleware", True),
    # 请求日志中间件由 tools.logger 顶层导入，无独立模块路径
    ("request_logging", None, "RequestLoggingMiddleware", False),
    ("request_size", "backend.middleware.request_size", "RequestSizeLimitMiddleware", True),
]

# 无独立模块路径的中间件（由 tools.logger 顶层导入），按类名索引
_MIDDLEWARE_LOCAL_CLASSES: dict[str, type] = {
    "RequestLoggingMiddleware": RequestLoggingMiddleware,
}


def _register_middlewares(app: FastAPI, logger) -> dict[str, str]:
    """
    注册全量中间件并返回每个中间件的加载状态。

    原先每个中间件各自 try/except/pass，任何导入失败都会导致鉴权体系
    静默消失且服务照常启动。这里改为统一收集状态：

    - 安全关键中间件（Auth/RBAC/RateLimit/RequestSizeLimit）失败 → ERROR 日志
    - 若 SECURITY_MIDDLEWARE_STRICT=True（默认）→ 直接抛错拒绝启动
    - 否则记录状态，由 /health 对外暴露，避免"裸奔而不自知"

    Args:
        app: FastAPI 应用实例
        logger: 日志记录器

    Returns:
        {中间件名: "loaded" | "failed"}

    Raises:
        RuntimeError: 严格模式下安全中间件加载失败
    """
    settings = get_settings()
    status: dict[str, str] = {}
    failed_critical: list[str] = []

    for name, module_path, class_name, critical in _MIDDLEWARE_SPEC:
        try:
            if module_path:
                middleware_cls = getattr(importlib.import_module(module_path), class_name)
            else:
                middleware_cls = _MIDDLEWARE_LOCAL_CLASSES[class_name]
            # type: ignore[arg-type]  # Starlette stub 将中间件类收窄为 factory
            app.add_middleware(middleware_cls)  # type: ignore[arg-type]
            status[name] = "loaded"
        except Exception as e:
            status[name] = "failed"
            if critical:
                failed_critical.append(name)
                logger.error(
                    "安全中间件 [{}] 加载失败: {} —— 缺失该防护会导致服务暴露", name, e
                )
            else:
                logger.warning("中间件 [{}] 加载失败，已跳过: {}", name, e)

    if failed_critical and settings.security_middleware_strict:
        raise RuntimeError(
            "安全中间件加载失败，拒绝启动（如需强行启动请设 "
            f"SECURITY_MIDDLEWARE_STRICT=False）: {', '.join(failed_critical)}"
        )

    return status


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

    # ── 关闭 Agent 依赖的外部连接池（MCP / A2A）──
    # 这些实例在 backend.api.dependencies 中惰性创建，此前从未被释放，
    # 长期运行或热重载会累积半开连接
    try:
        from backend.api.dependencies import close_dependencies
        await close_dependencies()
        logger.info("MCP / A2A 连接池已关闭")
    except Exception as e:
        logger.warning("关闭 MCP / A2A 连接池时出错: {}", e)

    # ── 关闭 Milvus 连接 ──
    try:
        from rag.retriever import close_retriever
        close_retriever()
        logger.info("Milvus 连接已关闭")
    except Exception as e:
        logger.warning("关闭 Milvus 连接时出错: {}", e)

    if tracing_manager is not None:
        try:
            await tracing_manager.shutdown()
        except Exception as e:
            logger.warning("关闭 Tracing 时出错: {}", e)
    try:
        from database.connection import close_db
        await close_db()
        logger.info("PostgreSQL 连接池已关闭")
    except Exception as e:
        logger.warning("关闭 PostgreSQL 连接池时出错: {}", e)
    try:
        from database.redis import close_redis
        await close_redis()
        logger.info("Redis 连接已关闭")
    except Exception as e:
        logger.warning("关闭 Redis 连接时出错: {}", e)


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

    # ── 中间件注册 ──
    # 顺序由 _MIDDLEWARE_SPEC 固定；安全中间件加载失败时按 SECURITY_MIDDLEWARE_STRICT
    # 决定是否拒绝启动，状态写入 app.state 供 /health 暴露
    logger = get_logger(__name__)
    middleware_status = _register_middlewares(app, logger)
    app.state.middleware_status = middleware_status
    logger.info("中间件注册完成: {}", middleware_status)

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
        # 中间件加载状态：任一安全中间件缺失时此处显示 failed，
        # 便于运维/前端对接方一眼看出服务是否处于无鉴权状态
        middleware_status = getattr(app.state, "middleware_status", {})
        degraded = any(
            name in ("auth", "rbac", "rate_limit", "request_size") and state == "failed"
            for name, state in middleware_status.items()
        )
        health = {
            "status": "degraded" if degraded else "healthy",
            "app": settings.app_name,
            "version": settings.app_version,
            "log_level": settings.log_level,
            "middleware": middleware_status,
        }
        # P4-7：schema 版本可查（alembic_version 表）。DB 不可达时非致命，保持 /health 语义纯净。
        try:
            from database.connection import get_schema_version

            ver = await get_schema_version()
            if ver:
                health["db_schema_version"] = ver["version_num"]
        except Exception as e:
            # DB 不可达时保持 /health 语义纯净（仍healthy），但留 debug 痕迹便于排查
            get_logger(__name__).debug("获取 DB schema 版本失败: {}", e)
        return health

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
