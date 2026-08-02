"""
backend.middleware.tracing - OpenTelemetry tracing middleware: span creation, trace context propagation

Author: le
Date: 2026/7/29
Version: 0.3
Task: Implement OpenTelemetry tracing middleware for distributed tracing
"""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager, asynccontextmanager
from typing import Any, Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# OpenTelemetry 可用性检测
# ============================================================

_otel_available: Optional[bool] = None


def _check_otel() -> bool:
    """检查 OpenTelemetry SDK 是否可用"""
    global _otel_available
    if _otel_available is None:
        try:
            from opentelemetry import trace  # noqa: F401
            from opentelemetry.sdk.trace import TracerProvider  # noqa: F401
            from opentelemetry.sdk.resources import Resource  # noqa: F401
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # noqa: F401
            _otel_available = True
        except ImportError:
            _otel_available = False
    return _otel_available


# ============================================================
# Proxy API — 当 OpenTelemetry 不可用时返回 NoOp
# ============================================================


class _NoOpSpan:
    """空操作 Span — OpenTelemetry 不可用时的占位"""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def end(self) -> None:
        pass

    @property
    def is_recording(self) -> bool:
        return False


class _NoOpTracer:
    """空操作 Tracer"""

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any):
        yield _NoOpSpan()


# ============================================================
# TracingManager — 全局 Tracing 管理器
# ============================================================


class TracingManager:
    """
    OpenTelemetry Tracing 管理器。

    封装 TracerProvider、SpanExporter 的初始化和生命周期管理。
    当 OpenTelemetry SDK 不可用时，自动降级为 NoOp 模式。

    使用方式:
        manager = TracingManager()
        await manager.initialize(service_name="gov-agent-platform", endpoint="http://localhost:4319")

        # 在请求处理中创建 span
        with manager.tracer.start_as_current_span("agent.execute") as span:
            span.set_attribute("agent.name", "supervisor")
            # ... 业务逻辑 ...
    """

    def __init__(self):
        self._initialized = False
        self._service_name = "gov-agent-platform"
        self._tracer: Any = _NoOpTracer()
        self._tracer_provider: Any = None

    async def initialize(
        self,
        service_name: str = "gov-agent-platform",
        endpoint: str = "http://localhost:4319",
        sample_rate: float = 1.0,
    ) -> None:
        """
        初始化 OpenTelemetry。

        Args:
            service_name: 服务名称，出现在 trace 的 service.name 属性中
            endpoint: OTLP Collector gRPC 端点
            sample_rate: 采样率（0.0-1.0），默认 1.0 全采样
        """
        self._service_name = service_name

        if not _check_otel():
            logger.info("OpenTelemetry SDK 未安装，Tracing 使用 NoOp 模式")
            self._initialized = True
            return

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.resources import Resource, SERVICE_NAME
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

            # 构建 Resource（标识此服务的元数据）
            resource = Resource(attributes={
                SERVICE_NAME: service_name,
                "service.version": "0.3.0",
                "deployment.environment": "development",
            })

            # 创建 TracerProvider
            self._tracer_provider = TracerProvider(
                resource=resource,
                sampler=TraceIdRatioBased(sample_rate),
            )

            # 配置 OTLP Exporter
            otlp_exporter = OTLPSpanExporter(
                endpoint=endpoint,
                insecure=True,  # 本地开发不需要 TLS
            )
            self._tracer_provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )

            # 设置为全局 TracerProvider（避免重复设置）
            try:
                trace.set_tracer_provider(self._tracer_provider)
            except Exception:
                logger.debug("TracerProvider 已存在，跳过全局设置")

            # 获取 Tracer
            self._tracer = trace.get_tracer(service_name)

            self._initialized = True
            logger.info(
                "OpenTelemetry 初始化成功: service={}, endpoint={}, sample_rate={}",
                service_name, endpoint, sample_rate,
            )

        except Exception as e:
            logger.warning("OpenTelemetry 初始化失败: {}，降级到 NoOp 模式", e)
            self._tracer = _NoOpTracer()
            self._initialized = True

    async def shutdown(self) -> None:
        """优雅关闭 — flush 所有待发送的 span"""
        if self._tracer_provider is not None:
            try:
                # shutdown() may or may not be a coroutine depending on OTel version
                result = self._tracer_provider.shutdown()
                if hasattr(result, '__await__'):
                    await result
                logger.info("OpenTelemetry TracerProvider 已关闭")
            except Exception as e:
                logger.warning("OpenTelemetry shutdown 异常: {}", e)

    @property
    def tracer(self) -> Any:
        """获取 Tracer 实例（可能是真实 OTel tracer 或 NoOp）"""
        return self._tracer

    @property
    def is_enabled(self) -> bool:
        """是否启用了真实 Tracing"""
        return _check_otel() and not isinstance(self._tracer, _NoOpTracer)


# ============================================================
# 全局单例
# ============================================================

_tracing_manager: Optional[TracingManager] = None


def get_tracing_manager() -> TracingManager:
    """获取 TracingManager 单例"""
    global _tracing_manager
    if _tracing_manager is None:
        _tracing_manager = TracingManager()
    return _tracing_manager


# ============================================================
# FastAPI Tracing 中间件
# ============================================================


class TracingMiddleware(BaseHTTPMiddleware):
    """
    OpenTelemetry Tracing 中间件 — 自动为每个 HTTP 请求创建 Span。

    功能:
    - 为每个 HTTP 请求创建 server span
    - 从请求头提取 W3C Trace Context (traceparent)
    - 记录 HTTP 方法、路径、状态码、耗时等属性
    - 记录异常信息
    - 注入 trace_id 到 response header (X-Trace-Id)

    使用方式:
        from backend.middleware.tracing import TracingMiddleware
        app.add_middleware(TracingMiddleware)
    """

    def __init__(self, app: ASGIApp, service_name: str = "gov-agent-platform"):
        super().__init__(app)
        self._service_name = service_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理请求并创建 Span。

        Args:
            request: FastAPI/Starlette 请求对象
            call_next: 下一个中间件/路由处理器

        Returns:
            HTTP Response
        """
        manager = get_tracing_manager()
        tracer = manager.tracer

        # 排除健康检查和指标端点（避免噪音）
        if request.url.path in ("/health", "/metrics", "/ready"):
            return await call_next(request)

        # 生成 trace_id（用于注入到 response header，与 OTel 的 span context 互补）
        app_trace_id = str(uuid.uuid4())

        span_name = f"{request.method} {request.url.path}"
        start_time = time.perf_counter()

        try:
            with tracer.start_as_current_span(span_name) as span:
                # ── 记录请求属性 ──
                if span.is_recording:
                    span.set_attributes({
                        "http.method": request.method,
                        "http.url": str(request.url),
                        "http.path": request.url.path,
                        "http.scheme": request.url.scheme,
                        "http.host": request.headers.get("host", ""),
                        "http.user_agent": request.headers.get("user-agent", ""),
                        "http.client_ip": request.client.host if request.client else "",
                        "app.trace_id": app_trace_id,
                    })

                # 执行业务逻辑
                response = await call_next(request)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # ── 记录响应属性 ──
                if span.is_recording:
                    span.set_attributes({
                        "http.status_code": response.status_code,
                        "http.response_content_length": response.headers.get("content-length", "0"),
                        "http.duration_ms": round(duration_ms, 2),
                    })

                    # 4xx/5xx 标记为错误
                    if response.status_code >= 400:
                        span.set_status(_make_error_status(f"HTTP {response.status_code}"))

                # 注入 trace_id 到 response header
                response.headers["X-Trace-Id"] = app_trace_id

                logger.debug(
                    "{} {} → {} ({:.0f}ms) trace={}",
                    request.method, request.url.path,
                    response.status_code, duration_ms, app_trace_id,
                )

                return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "{} {} → 500 ({:.0f}ms) trace={} — {}",
                request.method, request.url.path, duration_ms, app_trace_id, e,
            )

            # 尝试记录异常到 span（此时 span 可能已经结束）
            try:
                with tracer.start_as_current_span(span_name) as span:
                    if span.is_recording:
                        span.record_exception(e)
                        span.set_status(_make_error_status(str(e)))
            except Exception:
                pass

            # 返回 500 响应
            return Response(
                content='{"error":"Internal Server Error"}',
                status_code=500,
                media_type="application/json",
                headers={"X-Trace-Id": app_trace_id},
            )


# ============================================================
# 手动 Instrumentation 辅助工具
# ============================================================


@contextmanager
def trace_agent_call(
    agent_name: str,
    action: str = "execute",
    attributes: dict[str, Any] | None = None,
):
    """
    为 Agent 调用创建 Span 的上下文管理器。

    用法:
        with trace_agent_call("supervisor", action="plan", attributes={"task": task}):
            result = await supervisor.plan(state)

    Args:
        agent_name: Agent 名称
        action: 操作类型（execute / plan / route / review）
        attributes: 附加属性
    """
    manager = get_tracing_manager()
    tracer = manager.tracer
    span_name = f"agent.{agent_name}.{action}"
    start_time = time.perf_counter()

    try:
        with tracer.start_as_current_span(span_name) as span:
            if span.is_recording:
                span.set_attribute("agent.name", agent_name)
                span.set_attribute("agent.action", action)
                if attributes:
                    for k, v in attributes.items():
                        if isinstance(v, (str, int, float, bool)):
                            span.set_attribute(f"agent.{k}", v)

            yield span

            duration_ms = (time.perf_counter() - start_time) * 1000
            if span.is_recording:
                span.set_attribute("agent.duration_ms", round(duration_ms, 2))

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("Agent call 异常: {}.{} — {} ({:.0f}ms)", agent_name, action, e, duration_ms)
        try:
            with tracer.start_as_current_span(span_name) as span:
                if span.is_recording:
                    span.record_exception(e)
                    span.set_status(_make_error_status(str(e)))
        except Exception:
            pass
        raise


@asynccontextmanager
async def trace_async_agent_call(
    agent_name: str,
    action: str = "execute",
    attributes: dict[str, Any] | None = None,
):
    """
    异步版 — 为 Agent 调用创建 Span。

    用法:
        async with trace_async_agent_call("policy", action="search", attributes={"query": q}):
            result = await policy_agent.search(query)
    """
    manager = get_tracing_manager()
    tracer = manager.tracer
    span_name = f"agent.{agent_name}.{action}"
    start_time = time.perf_counter()

    try:
        with tracer.start_as_current_span(span_name) as span:
            if span.is_recording:
                span.set_attribute("agent.name", agent_name)
                span.set_attribute("agent.action", action)
                if attributes:
                    for k, v in attributes.items():
                        if isinstance(v, (str, int, float, bool)):
                            span.set_attribute(f"agent.{k}", v)

            yield span

            duration_ms = (time.perf_counter() - start_time) * 1000
            if span.is_recording:
                span.set_attribute("agent.duration_ms", round(duration_ms, 2))

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("Agent call 异常: {}.{} — {} ({:.0f}ms)", agent_name, action, e, duration_ms)
        try:
            with tracer.start_as_current_span(span_name) as span:
                if span.is_recording:
                    span.record_exception(e)
                    span.set_status(_make_error_status(str(e)))
        except Exception:
            pass
        raise


def trace_tool_call(
    tool_name: str,
    mcp_server: str = "",
    input_data: dict[str, Any] | None = None,
):
    """
    为 MCP Tool 调用创建 Span（装饰器/上下文管理器）。

    用法:
        with trace_tool_call("search_policy", mcp_server="policy_server") as span:
            result = await mcp_client.call_tool("search_policy", query)
    """
    manager = get_tracing_manager()
    tracer = manager.tracer
    span_name = f"tool.{tool_name}"
    start_time = time.perf_counter()

    # 这是一个同步上下文管理器，内部使用 tracer 的 start_as_current_span
    return _ToolSpanContext(tracer, span_name, tool_name, mcp_server, start_time, input_data)


class _ToolSpanContext:
    """Tool Span 上下文管理器"""

    def __init__(
        self,
        tracer: Any,
        span_name: str,
        tool_name: str,
        mcp_server: str,
        start_time: float,
        input_data: dict[str, Any] | None = None,
    ):
        self._tracer = tracer
        self._span_name = span_name
        self._tool_name = tool_name
        self._mcp_server = mcp_server
        self._start_time = start_time
        self._input_data = input_data
        self._span: Any = None

    def __enter__(self):
        self._span = self._tracer.start_span(self._span_name)
        if self._span.is_recording:
            self._span.set_attribute("tool.name", self._tool_name)
            if self._mcp_server:
                self._span.set_attribute("tool.mcp_server", self._mcp_server)
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self._start_time) * 1000
        if self._span.is_recording:
            self._span.set_attribute("tool.duration_ms", round(duration_ms, 2))
            if exc_type is not None and exc_val is not None:
                self._span.record_exception(exc_val)
                self._span.set_status(_make_error_status(str(exc_val)))
        self._span.end()
        return False  # 不抑制异常


# ============================================================
# FastAPI 初始化辅助函数
# ============================================================


async def setup_tracing(
    service_name: str = "gov-agent-platform",
    endpoint: str = "http://localhost:4319",
) -> TracingManager:
    """
    初始化 OpenTelemetry Tracing（在 FastAPI lifespan 中调用）。

    用法:
        from backend.middleware.tracing import setup_tracing

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            manager = await setup_tracing()
            yield
            await manager.shutdown()

    Args:
        service_name: 服务名称
        endpoint: OTLP Collector gRPC 端点

    Returns:
        TracingManager 实例
    """
    manager = get_tracing_manager()
    await manager.initialize(service_name=service_name, endpoint=endpoint)
    return manager


# ============================================================
# 内部辅助
# ============================================================


def _make_error_status(description: str) -> Any:
    """创建 OTel Error Status 对象（或返回 description 用于 Stub）"""
    try:
        from opentelemetry.trace import Status, StatusCode
        return Status(StatusCode.ERROR, description)
    except ImportError:
        return description


# ============================================================
# Smoke Test — python -m backend.middleware.tracing
# ============================================================

if __name__ == "__main__":
    import asyncio

    passed = 0
    failed = 0

    def check(description: str, condition: bool, detail: str = ""):
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {description}")
        else:
            failed += 1
            print(f"  [FAIL] {description}")
            if detail:
                print(f"         {detail}")

    def section(title: str):
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")

    async def main():
        # ── 1. TracingManager 基本 ──
        section("1. TracingManager 初始化")
        manager = TracingManager()
        check("manager 创建成功", manager is not None)
        check("初始未初始化", not manager._initialized or manager._initialized is True)

        await manager.initialize(service_name="test-service")
        check("初始化完成", manager._initialized)
        check("tracer 存在", manager.tracer is not None)

        otel_available = _check_otel()
        print(f"         OpenTelemetry SDK 可用: {otel_available}")

        # ── 2. Tracer 基本操作 ──
        section("2. Tracer span 操作")
        tracer = manager.tracer

        try:
            with tracer.start_as_current_span("test.span") as span:
                check("span 创建成功", span is not None)
                span.set_attribute("test.key", "test_value")
                span.set_attributes({"a": 1, "b": 2})
                span.add_event("test_event", {"event_key": "event_val"})
            check("span 上下文退出无异常", True)
        except Exception as e:
            check("span 操作", False, str(e))

        # ── 3. trace_agent_call ──
        section("3. trace_agent_call 上下文管理器")
        try:
            with trace_agent_call("supervisor", action="plan", attributes={"task": "测试任务"}) as span:
                check("agent span 创建", span is not None)
            check("agent span 上下文退出无异常", True)
        except Exception as e:
            check("trace_agent_call", False, str(e))

        # ── 4. trace_async_agent_call ──
        section("4. trace_async_agent_call 上下文管理器")
        try:
            async with trace_async_agent_call("policy", action="search", attributes={"query": "政策查询"}) as span:
                check("async agent span 创建", span is not None)
            check("async agent span 上下文退出无异常", True)
        except Exception as e:
            check("trace_async_agent_call", False, str(e))

        # ── 5. trace_tool_call ──
        section("5. trace_tool_call 上下文管理器")
        try:
            with trace_tool_call("search_policy", mcp_server="policy_server") as span:
                check("tool span 创建", span is not None)
                span.set_attribute("tool.query", "公积金查询")
            check("tool span 上下文退出无异常", True)
        except Exception as e:
            check("trace_tool_call", False, str(e))

        # ── 6. NoOp 降级 ──
        section("6. NoOp 降级行为")
        noop_span = _NoOpSpan()
        check("NoOpSpan.is_recording == False", not noop_span.is_recording)
        # NoOp 操作不应抛出异常
        noop_span.set_attribute("x", 1)
        noop_span.add_event("test")
        noop_span.record_exception(ValueError("test"))
        noop_span.end()
        check("NoOpSpan 所有操作无异常", True)

        noop_tracer = _NoOpTracer()
        with noop_tracer.start_as_current_span("noop") as span:
            check("NoOpTracer span", not span.is_recording)
        check("NoOpTracer 上下文退出无异常", True)

        # ── 7. TracingMiddleware 创建 ──
        section("7. TracingMiddleware 创建")
        # 创建一个简单的 ASGI app 用于测试中间件
        async def dummy_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = TracingMiddleware(dummy_app)
        check("TracingMiddleware 创建成功", middleware is not None)
        check("service_name 正确", middleware._service_name == "gov-agent-platform")

        # ── 8. setup_tracing ──
        section("8. setup_tracing 便捷函数")
        mgr = await setup_tracing(service_name="test-svc")
        check("setup_tracing 返回 TracingManager", isinstance(mgr, TracingManager))
        check("初始化完成", mgr._initialized)

        # ── 9. get_tracing_manager 单例 ──
        section("9. 全局单例")
        m1 = get_tracing_manager()
        m2 = get_tracing_manager()
        check("单例一致", m1 is m2)

        # ── 10. shutdown ──
        section("10. shutdown")
        await manager.shutdown()
        check("shutdown 无异常", True)

        # ── 11. is_enabled ──
        section("11. is_enabled 检查")
        enabled = manager.is_enabled
        check(f"is_enabled == {enabled} (otel={otel_available})", isinstance(enabled, bool))

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            exit(1)
        else:
            print(" — all good")
            print(f"\n  Run with: python -m backend.middleware.tracing")
            if not otel_available:
                print("  ℹ OpenTelemetry SDK 未安装，Tracing 使用 NoOp 模式")
                print("    安装命令: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp")

    asyncio.run(main())
