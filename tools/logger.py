"""
tools.logger - 项目统一日志模块

基于 loguru，实现：
- 结构化控制台输出（带颜色，从 ContextVar 实时读取 trace_id）
- 文件日志轮转（按天，30天保留，gzip压缩）
- 错误日志单独文件（90天保留）
- stdlib logging → loguru 桥接（第三方库如 langchain/uvicorn 也走 loguru）
- FastAPI 请求日志中间件（自动注入 trace_id）
- Agent 执行日志装饰器
- MCP 调用日志工具

运行时日志写入: gov_AP/logger/ 目录

Author: le
Date: 2026/7/29
Version: 0.2
Task: Unified logging module — relocated from backend/middleware/logging.py to tools/logger.py
"""
from __future__ import annotations

import logging as stdlib_logging
import os
import sys

# ── 确保项目根在 sys.path（python tools/logger.py 直接运行时需要） ──
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import time
import uuid
from contextvars import ContextVar
from typing import Any, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from loguru import logger as _loguru_logger

from backend.config import Settings


# ============================================================
# 日志输出目录
# ============================================================

LOG_DIR = "logger"


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

    return "{time} | {level: <8} | {trace} | {user} | {agent} | {source} | {message}{ex}\n".format(
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

    return "{time} | {level} | {trace} | {source} | {message}{ex}\n".format(
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

    1. 创建 logger/ 目录
    2. 移除所有已有 handler
    3. 添加控制台输出（debug模式带颜色和diagnose）
    4. 添加文件输出（按天轮转，保留30天，gzip压缩）
    5. 错误日志单独文件（90天保留）
    6. 桥接 stdlib logging → loguru

    Args:
        settings: 应用配置（包含 log_level 等）
    """
    os.makedirs(LOG_DIR, exist_ok=True)

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

    # ── 运行日志 ──
    _loguru_logger.add(
        os.path.join(LOG_DIR, "app_{time:YYYY-MM-DD}.log"),
        format=_file_format,
        level="INFO",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
    )

    # ── 错误日志 ──
    _loguru_logger.add(
        os.path.join(LOG_DIR, "error_{time:YYYY-MM-DD}.log"),
        format=_error_file_format,
        level="ERROR",
        rotation="00:00",
        retention="90 days",
        encoding="utf-8",
    )

    # ── 桥接 stdlib → loguru ──
    _bridge_stdlib_logging()

    _loguru_logger.info(
        "日志系统初始化完成 level={} debug={} dir={}",
        level, settings.debug, LOG_DIR,
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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI 请求日志中间件。

    为每个 HTTP 请求自动:
    1. 提取或生成 trace_id（Header: X-Trace-Id → 自动生成）
    2. 设置 ContextVar（下游代码通过 get_current_trace_id() 获取）
    3. 记录请求开始/结束（method, path, status_code, latency_ms）
    4. 注入 X-Trace-Id 和 X-Process-Time-ms 到响应头
    5. 请求结束后清理 ContextVar

    使用方式:
        from tools.logger import RequestLoggingMiddleware
        app.add_middleware(RequestLoggingMiddleware)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or f"trace_{uuid.uuid4().hex[:16]}"
        user_id = request.headers.get("X-User-Id", "-")

        token = _trace_id_ctx.set(trace_id)
        user_token = _user_id_ctx.set(user_id)

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
        _loguru_logger.info(
            "<-- {} {} {} {:.1f}ms",
            request.method, request.url.path, response.status_code, elapsed,
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


# ============================================================
# Smoke Test — python tools/logger.py
# ============================================================


def _now_str() -> str:
    """当前日期字符串 YYYY-MM-DD，供测试用"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


if __name__ == "__main__":
    import glob
    import os

    passed = 0
    failed = 0

    def check(name: str, ok: bool, detail: str = ""):
        global passed, failed
        if ok:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")
            if detail:
                print(f"         {detail}")

    # ── 1. 初始化（用最小 Settings mock，不依赖 .env） ──
    print("\n" + "=" * 60)
    print("  1. 初始化")
    print("=" * 60)

    from dataclasses import dataclass

    @dataclass
    class _FakeSettings:
        log_level: str = "DEBUG"
        debug: bool = True

    fake_settings = _FakeSettings()

    # 清理旧日志
    import shutil
    if os.path.isdir(LOG_DIR):
        shutil.rmtree(LOG_DIR)

    setup_logging(fake_settings)
    check("setup_logging 不抛异常", True)
    check("logger/ 目录已创建", os.path.isdir(LOG_DIR))

    # ── 2. 控制台输出（各日志级别） ──
    print("\n" + "=" * 60)
    print("  2. 控制台输出（各日志级别）")
    print("=" * 60)

    test_logger = get_logger("smoke_test")

    print("  --- 以下为日志输出，请目视检查 ---")
    test_logger.debug("DEBUG 级别日志（仅 debug=True 时显示）")
    test_logger.info("INFO 级别日志 — 正常信息")
    test_logger.warning("WARNING 级别日志 — 警告")
    test_logger.error("ERROR 级别日志 — 错误（不含异常）")
    print("  --- 日志输出结束 ---")
    check("各级别日志无异常", True, "目视确认上方5行日志是否出现")

    # ── 3. trace_id 上下文绑定 ──
    print("\n" + "=" * 60)
    print("  3. trace_id / user_id / agent_name 绑定")
    print("=" * 60)

    set_trace_context("trace_abc123def45678", user_id="test_user", agent_name="supervisor")
    tid = get_current_trace_id()
    uid = get_current_user_id()
    aid = get_current_agent_name()
    check("get_current_trace_id()", tid == "trace_abc123def45678", tid)
    check("get_current_user_id()", uid == "test_user", uid)
    check("get_current_agent_name()", aid == "supervisor", aid)

    print("  --- 带 trace 上下文的日志 ---")
    test_logger.bind().info("这条日志应该带上 trace_abc 前缀")
    print("  --- 日志输出结束 ---")

    log_mcp_call(
        server_name="policy_server",
        tool_name="search_policy",
        input_args={"query": "开餐馆需要什么材料", "top_k": 5},
        latency_ms=234.5,
    )

    log_mcp_call(
        server_name="material_server",
        tool_name="check_material",
        input_args={"file_id": "doc_001"},
        status="failed",
        error="OCR 服务超时",
    )
    check("log_mcp_call 成功/失败均无异常", True)

    # ── 4. 异常捕获 + Traceback ──
    print("\n" + "=" * 60)
    print("  4. 异常捕获 + Traceback")
    print("=" * 60)

    print("  --- 以下为带 traceback 的 ERROR 日志 ---")
    try:
        data = {"policy": "食品经营许可条例"}
        _ = data["nonexistent_key"]  # KeyError
    except KeyError:
        test_logger.exception("捕获 KeyError — 应显示完整 traceback")
    print("  --- 日志输出结束 ---")
    check("exception() 不抛异常", True, "目视确认上方 traceback")

    # ── 5. Agent 执行日志装饰器 ──
    print("\n" + "=" * 60)
    print("  5. Agent 执行日志装饰器")
    print("=" * 60)

    import asyncio

    @log_agent_call("supervisor")
    async def fake_agent_node(state: dict) -> dict:
        """模拟 Agent 节点：干1ms活，返回带 mcp_history 的 state"""
        await asyncio.sleep(0.001)
        return {"mcp_history": [{"tool": "search_policy"}, {"tool": "check_material"}]}

    print("  --- 以下为 Agent 装饰器日志 ---")
    result = asyncio.run(fake_agent_node({"user_query": "test"}))
    print("  --- 日志输出结束 ---")
    check("@log_agent_call 正常完成", "mcp_history" in result)
    check("装饰器恢复了 agent_name ContextVar",
          get_current_agent_name() == aid,
          f"expected={aid}, got={get_current_agent_name()}"
    )

    # 测试装饰器 + 异常
    @log_agent_call("policy")
    async def failing_agent(state: dict) -> dict:
        raise ValueError("模拟 Agent 崩溃")

    print("  --- 以下为 Agent 异常日志 ---")
    try:
        asyncio.run(failing_agent({"query": "test"}))
    except ValueError:
        pass
    print("  --- 日志输出结束 ---")
    check("@log_agent_call 异常日志正常", True)

    # ── 6. 文件日志验证 ──
    print("\n" + "=" * 60)
    print("  6. 文件日志")
    print("=" * 60)

    import time as _time
    _time.sleep(0.3)  # 等 loguru flush

    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "*.log")))
    check("logger/ 下有日志文件", len(log_files) > 0, f"找到 {len(log_files)} 个文件")

    app_file = os.path.join(LOG_DIR, f"app_{_now_str()}.log")
    error_file = os.path.join(LOG_DIR, f"error_{_now_str()}.log")

    check(f"APP 日志存在: {os.path.basename(app_file)}",
          os.path.exists(app_file),
          f"路径: {app_file}")

    # 读取 app 日志验证内容
    if os.path.exists(app_file):
        with open(app_file, encoding="utf-8") as f:
            app_content = f.read()
        check("APP 日志含 INFO 级别",
              "INFO" in app_content,
              f"文件大小: {len(app_content)} bytes")
        check("APP 日志含 trace_abc",
              "trace_abc" in app_content,
              "trace_id 写入文件")
        check("APP 日志含 MCP调用",
              "MCP调用" in app_content,
              "MCP 调用记录写入文件")
        check("APP 日志含 ERROR 级别",
              "ERROR" in app_content,
              "异常日志写入文件")

    # 错误日志
    if os.path.exists(error_file):
        with open(error_file, encoding="utf-8") as f:
            error_content = f.read()
        check(f"ERROR 日志存在: {os.path.basename(error_file)}",
              os.path.exists(error_file))
        check("ERROR 日志含 traceback",
              "Traceback" in error_content or "KeyError" in error_content,
              f"文件大小: {len(error_content)} bytes")

    # ── 7. 清理 ──
    print("\n" + "=" * 60)
    print("  7. 清理")
    print("=" * 60)

    # 先停止 loguru 的所有 handler（释放文件锁，Windows 必需）
    _loguru_logger.remove()
    import shutil
    if os.path.isdir(LOG_DIR):
        shutil.rmtree(LOG_DIR)
        check("测试文件已清理", not os.path.exists(LOG_DIR))

    # ── Summary ──
    total = passed + failed
    print(f"\n{'='*60}")
    print(f"  RESULT: {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
    else:
        print(" — 日志系统正常")
    print(f"{'='*60}")
    print(f"  运行方式: python tools/logger.py\n")
