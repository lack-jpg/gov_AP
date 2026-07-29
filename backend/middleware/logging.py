"""
backend.middleware.logging - Request logging middleware: trace_id injection, request/response logging

基于 loguru，实现：
- 结构化控制台输出（带颜色，从 ContextVar 实时读取 trace_id）
- 文件日志轮转（按天，30天保留，gzip压缩）
- 错误日志单独文件
- stdlib logging → loguru 桥接（第三方库如 langchain/uvicorn 也走 loguru）
- FastAPI 请求日志中间件（自动注入 trace_id）
- Agent 执行日志装饰器
- MCP 调用日志工具

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement structured logging middleware with trace_id propagation
"""
from __future__ import annotations

import logging as stdlib_logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Optional

from fastapi import Request, Response
from loguru import logger as _loguru_logger

from backend.config import Settings


# ============================================================
# ContextVar — 跨协程传递 trace_id / user_id / agent_name
# ============================================================

_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")
_user_id_ctx: ContextVar[str] = ContextVar("user_id", default="")
_agent_name_ctx: ContextVar[str] = ContextVar("agent_name", default="")


def set_trace_context(trace_id: str, user_id: str = "", agent_name: str = "") -> None:
    """在当前协程上下文中设置 trace_id / user_id / agent_name"""
    _trace_id_ctx.set(trace_id)
    if user_id:
        _user_id_ctx.set(user_id)
    if agent_name:
        _agent_name_ctx.set(agent_name)


def get_current_trace_id() -> str:
    """获取当前协程的 trace_id，为空时返回 '-' """
    return _trace_id_ctx.get() or "-"


def get_current_user_id() -> str:
    """获取当前协程的 user_id，为空时返回 '-' """
    return _user_id_ctx.get() or "-"


def get_current_agent_name() -> str:
    """获取当前协程的 agent_name，为空时返回 '-' """
    return _agent_name_ctx.get() or "-"


# ============================================================
# 日志格式化函数
# ============================================================


def _console_format(record: dict[str, Any]) -> str:
    """
    控制台格式 — 带颜色，所有字段通过 str.format() 显式传入。

    ⚠️ 全部字段由 python format() 拼接，不使用 loguru 的 {name} / {extra[x]}
    插值标记——因为 record["name"] 可能包含 `__main__`（含 `<module>`），
    `<module>` 中的尖括号会被 loguru colorizer 误解析为颜色标签导致 ValueError。
    """
    trace_id = _trace_id_ctx.get() or "-"
    user_id = _user_id_ctx.get() or "-"
    agent = _agent_name_ctx.get() or "-"
    source = "{}:{}".format(record.get("name", "?"), record.get("line", "?"))

    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{trace}</cyan> | "
        "<yellow>{user}</yellow> | "
        "<blue>{agent: <14}</blue> | "
        "{source} | "
        "<level>{message}</level>\n"
        "{exception}"
    ).format(
        time=record["time"],
        level=record["level"].name,
        trace=trace_id[:14],
        user=user_id,
        agent=agent,
        source=source,
        message=record["message"],
        exception=_format_exception(record.get("exception"), escape_angles=True),
    )
def _file_format(record: dict[str, Any]) -> str:
    """
    文件格式 — 无颜色，纯文本，适合 grep / ELK 采集。

    同样绕过 loguru 插值标记，直接从 ContextVar 读取。
    """
    trace_id = _trace_id_ctx.get() or "-"
    user_id = _user_id_ctx.get() or "-"
    agent = _agent_name_ctx.get() or "-"
    source = "{}:{}".format(record.get("name", "?"), record.get("line", "?"))

    return "{time} | {level: <8} | {trace} | {user} | {agent} | {source} | {message}{ex}".format(
        time=record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        level=record["level"].name,
        trace=trace_id[:14],
        user=user_id,
        agent=agent,
        source=source,
        message=record["message"],
        ex=_format_exception(record.get("exception"), escape_angles=True),
    )


def _error_file_format(record: dict[str, Any]) -> str:
    """错误日志文件格式 — 精简版"""
    trace_id = _trace_id_ctx.get() or "-"
    source = "{}:{}".format(record.get("name", "?"), record.get("line", "?"))

    return "{time} | {level} | {trace} | {source} | {message}{ex}".format(
        time=record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        level=record["level"].name,
        trace=trace_id[:14],
        source=source,
        message=record["message"],
        ex=_format_exception(record.get("exception"), escape_angles=True),
    )


def _format_exception(exc: Any, escape_angles: bool = False) -> str:
    """
    格式化 loguru record 中的 exception 字段。

    record["exception"] 是 RecordException namedtuple(type, value, traceback)
    或 None（无异常时）。

    escape_angles=True 时转义 `<` 以防止 loguru colorizer 把文件名中的
    `<>`（如 `<string>`、`<module>`）误解析为颜色指令。
    """
    if exc is None:
        return ""
    import traceback as tb
    if hasattr(exc, "traceback"):
        text = "".join(tb.format_exception(exc.type, exc.value, exc.traceback))
    elif isinstance(exc, BaseException):
        text = "".join(tb.format_exception(type(exc), exc, exc.__traceback__))
    else:
        text = str(exc)
    if escape_angles:
        text = text.replace("<", "\\<")
    return "\n" + text


# ============================================================
# setup_logging — 日志系统初始化
# ============================================================


def setup_logging(settings: Settings) -> None:
    """
    初始化日志系统。

    1. 创建 logs/ 目录
    2. 移除所有已有 handler
    3. 添加控制台输出（debug模式带颜色和diagnose）
    4. 添加文件输出（按天轮转，保留30天，gzip压缩）
    5. 错误日志单独文件（90天保留）
    6. 桥接 stdlib logging → loguru
    """
    os.makedirs("logs", exist_ok=True)

    level = settings.log_level.upper()

    # 移除默认 handler
    _loguru_logger.remove()

    # ── 控制台输出 ──
    _loguru_logger.add(
        sys.stderr,
        format=_console_format,
        level=level,
        colorize=settings.debug,
        backtrace=settings.debug,
        diagnose=settings.debug,
    )

    # ── 文件输出 ──
    _loguru_logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        format=_file_format,
        level="INFO",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
    )

    # ── 错误日志 ──
    _loguru_logger.add(
        "logs/error_{time:YYYY-MM-DD}.log",
        format=_error_file_format,
        level="ERROR",
        rotation="00:00",
        retention="90 days",
        encoding="utf-8",
    )

    # ── 桥接 stdlib → loguru ──
    _bridge_stdlib_logging()

    _loguru_logger.info(
        "日志系统初始化完成 level={} debug={}", level, settings.debug
    )


def _bridge_stdlib_logging() -> None:
    """将标准库 logging 的输出重定向到 loguru"""

    class _LoguruHandler(stdlib_logging.Handler):
        def emit(self, record: stdlib_logging.LogRecord) -> None:
            level_map = {
                stdlib_logging.DEBUG: "DEBUG",
                stdlib_logging.INFO: "INFO",
                stdlib_logging.WARNING: "WARNING",
                stdlib_logging.ERROR: "ERROR",
                stdlib_logging.CRITICAL: "CRITICAL",
            }
            level_name = level_map.get(record.levelno, "INFO")
            _loguru_logger.opt(
                depth=0, exception=record.exc_info,
            ).log(level_name, "[{}] {}", record.name, record.getMessage())

    root = stdlib_logging.getLogger()
    root.handlers = [_LoguruHandler()]
    root.setLevel(stdlib_logging.INFO)


# ============================================================
# 获取 logger
# ============================================================


def get_logger(name: str = __name__):
    """
    获取 loguru logger（绑定 name）。

    用法:
        logger = get_logger(__name__)
        logger.info("处理请求")
        # 控制台输出自动包含 trace_id / user_id / agent_name
        # 文件日志同样包含（从 ContextVar 实时读取）

    Args:
        name: logger名称（通常是 __name__）

    Returns:
        loguru BoundLogger
    """
    return _loguru_logger.bind(name=name)


# 模块级 logger
logger = _loguru_logger


# ============================================================
# FastAPI 请求日志中间件
# ============================================================


class RequestLoggingMiddleware:
    """
    FastAPI 请求日志中间件。

    为每个 HTTP 请求:
    1. 提取或生成 trace_id（Header: X-Trace-Id）
    2. 设置 ContextVar（所有下游代码通过 get_current_trace_id() 获取）
    3. 记录请求开始/结束（method, path, status, latency）
    4. 注入 X-Trace-Id 和 X-Process-Time-ms 到响应头
    5. 请求结束后清理 ContextVar

    使用方式:
        app.add_middleware(RequestLoggingMiddleware)
    """

    async def __call__(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or f"trace_{uuid.uuid4().hex[:16]}"
        user_id = request.headers.get("X-User-Id", "-")

        token = _trace_id_ctx.set(trace_id)
        user_token = _user_id_ctx.set(user_id)
        request.state.trace_id = trace_id
        request.state.user_id = user_id

        start = time.perf_counter()
        _loguru_logger.info("--> {} {}", request.method, request.url.path)

        try:
            response = await call_next(request)
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            _loguru_logger.error(
                "<-- {} {} 500 {:.1f}ms",
                request.method, request.url.path, elapsed,
            )
            raise

        elapsed = (time.perf_counter() - start) * 1000
        status_code = getattr(response, "status_code", 0)
        _loguru_logger.info(
            "<-- {} {} {} {:.1f}ms",
            request.method, request.url.path, status_code, elapsed,
        )

        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Process-Time-ms"] = f"{elapsed:.1f}"

        _trace_id_ctx.reset(token)
        _user_id_ctx.reset(user_token)

        return response


# ============================================================
# Agent 执行日志装饰器
# ============================================================


def log_agent_call(agent_name: str):
    """
    装饰器：自动记录 Agent 调用的开始、完成（含耗时和步骤数）、失败。

    用法:
        @log_agent_call("supervisor")
        async def supervisor_node(state): ...

    日志输出:
        [supervisor] 开始执行
        [supervisor] 执行完成 latency=234ms steps=1
        [supervisor] 执行失败 latency=120ms error=...
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            token = _agent_name_ctx.set(agent_name)
            start = time.perf_counter()

            _loguru_logger.info("[{}] 开始执行", agent_name)

            try:
                result = await func(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                steps = len(result.get("mcp_history", [])) if isinstance(result, dict) else 0
                _loguru_logger.info(
                    "[{}] 执行完成 latency={:.1f}ms steps={}",
                    agent_name, elapsed, steps,
                )
                return result
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                _loguru_logger.error(
                    "[{}] 执行失败 latency={:.1f}ms error={}",
                    agent_name, elapsed, e,
                )
                raise
            finally:
                _agent_name_ctx.reset(token)

        return wrapper

    return decorator


# ============================================================
# MCP 调用日志
# ============================================================


def log_mcp_call(
    server_name: str,
    tool_name: str,
    input_args: dict[str, Any],
    output_result: Optional[dict[str, Any]] = None,
    latency_ms: float = 0.0,
    status: str = "success",
    error: Optional[str] = None,
) -> None:
    """
    记录一次MCP工具调用。

    示例输出:
        MCP调用 | policy_server | search_policy | status=success | latency=234ms
    """
    args_summary = _summarize_dict(input_args, max_len=80)
    msg = (
        f"MCP调用 | {server_name} | {tool_name} | "
        f"status={status} | latency={latency_ms:.1f}ms"
    )
    if args_summary:
        msg += f" | args={args_summary}"
    if error:
        msg += f" | error={error}"

    _loguru_logger.info(msg)


def _summarize_dict(d: dict[str, Any], max_len: int = 80) -> str:
    """生成字典摘要，截断过长内容"""
    parts = []
    for k, v in d.items():
        s = str(v)
        if len(s) > 40:
            s = s[:37] + "..."
        parts.append(f"{k}={s}")
    result = ", ".join(parts)
    if len(result) > max_len:
        result = result[:max_len - 3] + "..."
    return result
