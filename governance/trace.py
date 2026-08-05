"""
governance.trace - Full-chain trace: record trace_id, agent, tool, latency, token_usage for every call

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement OpenTelemetry-based Agent trace collection and storage
"""
from __future__ import annotations

import contextvars
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Iterator

from tools.logger import get_logger as _trace_get_logger

_trace_logger = _trace_get_logger(__name__)


# ============================================================
# Span 类型枚举
# ============================================================


class SpanKind(str, Enum):
    """Span 类型 — 对应 OpenTelemetry SpanKind"""
    AGENT = "agent"       # Agent 调用
    TOOL = "tool"         # 工具调用（MCP）
    LLM = "llm"           # LLM 调用
    NODE = "node"         # LangGraph 节点
    TASK = "task"         # 顶层任务


class SpanStatus(str, Enum):
    """Span 执行状态"""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


# ============================================================
# TraceContext — 上下文传播
# ============================================================


@dataclass
class TraceInfo:
    """追踪元信息"""
    trace_id: str
    span_id: str
    parent_span_id: str | None = None

    def child(self) -> TraceInfo:
        """创建子 span 的 TraceInfo"""
        return TraceInfo(
            trace_id=self.trace_id,
            span_id=_gen_span_id(),
            parent_span_id=self.span_id,
        )


# 使用 contextvars 实现异步安全的上下文传播
_current_trace: contextvars.ContextVar[TraceInfo | None] = contextvars.ContextVar(
    "current_trace", default=None
)

# 当前正在执行的 Agent 名称（供 LLM callback 记录 token 用量时归属）
_current_agent_name: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_agent_name", default="llm"
)


def get_current_trace() -> TraceInfo | None:
    """获取当前协程的 trace 信息"""
    return _current_trace.get()


def set_current_trace(trace: TraceInfo | None) -> None:
    """设置当前协程的 trace 信息"""
    _current_trace.set(trace)


def get_current_agent_name() -> str:
    """获取当前协程正在执行的 Agent 名称（默认 'llm'）"""
    return _current_agent_name.get()


def set_current_agent_name(name: str) -> None:
    """设置当前协程的 Agent 名称"""
    _current_agent_name.set(name)


# ============================================================
# Span 数据类
# ============================================================


@dataclass
class SpanRecord:
    """一次调用的完整 span 记录"""
    trace_id: str
    span_id: str
    parent_span_id: str | None
    kind: SpanKind
    agent_name: str | None = None       # Agent 名称
    node_name: str | None = None         # LangGraph 节点名
    tool_name: str | None = None         # MCP 工具名
    input_data: str | None = None        # 输入（JSON 字符串）
    output_data: str | None = None       # 输出（JSON 字符串）
    input_tokens: int = 0                # LLM 输入 token
    output_tokens: int = 0               # LLM 输出 token
    latency_ms: float = 0.0              # 耗时（毫秒）
    status: SpanStatus = SpanStatus.RUNNING
    error_message: str | None = None
    risk_level: str = "low"              # low | medium | high | critical
    metadata: dict[str, Any] | None = None
    started_at: float = 0.0              # epoch 秒（time.perf_counter）
    ended_at: float = 0.0

    def to_db_dict(self) -> dict[str, Any]:
        """转为数据库 Trace 模型兼容的字典"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "agent_name": self.agent_name or "",
            "node_name": self.node_name,
            "tool_name": self.tool_name,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "status": self.status.value,
            "error_message": self.error_message,
            "risk_level": self.risk_level,
            "metadata_": self.metadata,
        }

    def to_summary(self) -> dict[str, Any]:
        """摘要信息（不含大 payload）"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "kind": self.kind.value,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "latency_ms": self.latency_ms,
            "token_usage": self.input_tokens + self.output_tokens,
            "status": self.status.value,
        }


# ============================================================
# TraceRecorder — 记录器
# ============================================================


class TraceRecorder:
    """
    Trace 记录器：收集 span 并持久化到数据库。

    支持两种模式：
    1. DB 模式：通过 async session 写入 PostgreSQL
    2. Memory 模式：存储到内存列表（测试用）
    """

    def __init__(self) -> None:
        self._spans: list[SpanRecord] = []

    @property
    def spans(self) -> list[SpanRecord]:
        """所有已记录的 span"""
        return list(self._spans)

    def record(self, span: SpanRecord) -> None:
        """
        记录一个 span 到内存。

        Args:
            span: SpanRecord 实例
        """
        self._spans.append(span)

    def get_spans_by_trace(self, trace_id: str) -> list[SpanRecord]:
        """
        按 trace_id 过滤 span。

        Args:
            trace_id: 追踪 ID

        Returns:
            该 trace 的所有 span
        """
        return [s for s in self._spans if s.trace_id == trace_id]

    def get_spans_by_agent(self, agent_name: str) -> list[SpanRecord]:
        """
        按 agent_name 过滤 span。

        Args:
            agent_name: Agent 名称

        Returns:
            该 agent 的所有 span
        """
        return [s for s in self._spans if s.agent_name == agent_name]

    def get_stats(self, trace_id: str | None = None) -> dict[str, Any]:
        """
        获取统计摘要。

        Args:
            trace_id: 可选，按 trace 过滤

        Returns:
            统计数据字典
        """
        spans = self._spans if trace_id is None else self.get_spans_by_trace(trace_id)

        if not spans:
            return {"total_spans": 0}

        agent_spans = [s for s in spans if s.kind == SpanKind.AGENT]
        tool_spans = [s for s in spans if s.kind == SpanKind.TOOL]
        llm_spans = [s for s in spans if s.kind == SpanKind.LLM]

        total_tokens = sum(s.input_tokens + s.output_tokens for s in llm_spans)
        avg_latency = sum(s.latency_ms for s in spans) / len(spans)

        return {
            "total_spans": len(spans),
            "agent_calls": len(agent_spans),
            "tool_calls": len(tool_spans),
            "llm_calls": len(llm_spans),
            "total_tokens": total_tokens,
            "avg_latency_ms": round(avg_latency, 2),
            "success_count": sum(1 for s in spans if s.status == SpanStatus.SUCCESS),
            "failed_count": sum(1 for s in spans if s.status == SpanStatus.FAILED),
        }

    async def flush_to_db(
        self, trace_id: str | None = None
    ) -> int:
        """
        将内存中的 span 写入数据库。

        Args:
            trace_id: 可选，仅写入指定 trace 的 span

        Returns:
            写入的记录数
        """
        spans = self._spans if trace_id is None else self.get_spans_by_trace(trace_id)

        if not spans:
            return 0

        try:
            from database.connection import get_session_factory
            from database.models import Trace

            session_factory = get_session_factory()
            async with session_factory() as session:
                for span in spans:
                    trace = Trace(**span.to_db_dict())
                    session.add(trace)
                await session.commit()
            return len(spans)
        except Exception as e:
            # DB 不可达时，span 已保留在内存中，下次可重试
            _trace_logger.warning("Trace flush to DB 失败（span 保留在内存）: {}", e)
            return 0

    def clear(self) -> None:
        """清空内存中的所有 span"""
        self._spans.clear()


# ============================================================
# 全局 TraceRecorder 单例
# ============================================================


_trace_recorder: TraceRecorder | None = None


def get_trace_recorder() -> TraceRecorder:
    """获取全局 TraceRecorder 单例"""
    global _trace_recorder
    if _trace_recorder is None:
        _trace_recorder = TraceRecorder()
    return _trace_recorder


def reset_trace_recorder() -> None:
    """重置全局 TraceRecorder（测试用）"""
    global _trace_recorder
    _trace_recorder = TraceRecorder()


# ============================================================
# AgentTracer — Agent 调用追踪
# ============================================================


class AgentTracer:
    """
    Agent 调用追踪器 — 用于装饰或上下文管理器。

    用法（装饰器）:
        @AgentTracer.trace(agent_name="policy", kind=SpanKind.AGENT)
        async def query_policy(query: str) -> str: ...

    用法（上下文管理器）:
        async with AgentTracer.span(agent_name="policy") as span:
            result = await agent.run()
            span.record_output(result)
    """

    @staticmethod
    @asynccontextmanager
    async def span(
        agent_name: str,
        kind: SpanKind = SpanKind.AGENT,
        tool_name: str | None = None,
        node_name: str | None = None,
        input_data: str | None = None,
    ) -> AsyncIterator[SpanInProgress]:
        """
        创建一个追踪 span 的异步上下文管理器。

        Args:
            agent_name: Agent 名称
            kind: Span 类型
            tool_name: 工具名（仅 TOOL span）
            node_name: 节点名（仅 NODE span）
            input_data: 输入数据

        Yields:
            SpanInProgress 实例，用于记录输出和状态
        """
        parent = get_current_trace()

        # 如果是根 span，创建新的 trace
        if parent is None:
            trace = TraceInfo(
                trace_id=_gen_trace_id(),
                span_id=_gen_span_id(),
            )
        else:
            trace = parent.child()

        set_current_trace(trace)
        _agent_token = _current_agent_name.set(agent_name)

        span_record = SpanRecord(
            trace_id=trace.trace_id,
            span_id=trace.span_id,
            parent_span_id=trace.parent_span_id,
            kind=kind,
            agent_name=agent_name,
            node_name=node_name,
            tool_name=tool_name,
            input_data=input_data,
            status=SpanStatus.RUNNING,
            started_at=time.perf_counter(),
        )

        in_progress = SpanInProgress(span_record)

        try:
            yield in_progress
            # 正常完成
            span_record.status = SpanStatus.SUCCESS
        except Exception as exc:
            span_record.status = SpanStatus.FAILED
            span_record.error_message = str(exc)
            span_record.risk_level = "high"
            raise
        finally:
            span_record.ended_at = time.perf_counter()
            span_record.latency_ms = (span_record.ended_at - span_record.started_at) * 1000.0
            get_trace_recorder().record(span_record)
            # 恢复父 context
            set_current_trace(parent)
            _current_agent_name.reset(_agent_token)

    @staticmethod
    @contextmanager
    def span_sync(
        agent_name: str,
        kind: SpanKind = SpanKind.AGENT,
        tool_name: str | None = None,
        node_name: str | None = None,
        input_data: str | None = None,
    ) -> Iterator[SpanInProgress]:
        """同步版本的 span 上下文管理器"""
        parent = get_current_trace()

        if parent is None:
            trace = TraceInfo(
                trace_id=_gen_trace_id(),
                span_id=_gen_span_id(),
            )
        else:
            trace = parent.child()

        set_current_trace(trace)
        _agent_token = _current_agent_name.set(agent_name)

        span_record = SpanRecord(
            trace_id=trace.trace_id,
            span_id=trace.span_id,
            parent_span_id=trace.parent_span_id,
            kind=kind,
            agent_name=agent_name,
            node_name=node_name,
            tool_name=tool_name,
            input_data=input_data,
            status=SpanStatus.RUNNING,
            started_at=time.perf_counter(),
        )

        in_progress = SpanInProgress(span_record)

        try:
            yield in_progress
            span_record.status = SpanStatus.SUCCESS
        except Exception as exc:
            span_record.status = SpanStatus.FAILED
            span_record.error_message = str(exc)
            span_record.risk_level = "high"
            raise
        finally:
            span_record.ended_at = time.perf_counter()
            span_record.latency_ms = (span_record.ended_at - span_record.started_at) * 1000.0
            get_trace_recorder().record(span_record)
            set_current_trace(parent)
            _current_agent_name.reset(_agent_token)

    @staticmethod
    def trace(
        agent_name: str,
        kind: SpanKind = SpanKind.AGENT,
    ):
        """
        装饰器工厂：在 Agent 函数调用周围自动创建 span。

        Args:
            agent_name: Agent 名称
            kind: Span 类型

        Returns:
            装饰器
        """
        def decorator(func):
            import functools

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                async with AgentTracer.span(
                    agent_name=agent_name, kind=kind
                ) as span:
                    result = await func(*args, **kwargs)
                    span.record_output(str(result)[:2048])
                    return result

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                with AgentTracer.span_sync(
                    agent_name=agent_name, kind=kind
                ) as span:
                    result = func(*args, **kwargs)
                    span.record_output(str(result)[:2048])
                    return result

            import asyncio
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper

        return decorator


class SpanInProgress:
    """进行中的 span，用于在上下文管理器内记录额外数据"""

    def __init__(self, record: SpanRecord) -> None:
        self._record = record

    @property
    def trace_id(self) -> str:
        return self._record.trace_id

    @property
    def span_id(self) -> str:
        return self._record.span_id

    def record_output(self, output: str | None) -> None:
        """记录输出数据"""
        self._record.output_data = output

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """记录 LLM token 用量"""
        self._record.input_tokens = input_tokens
        self._record.output_tokens = output_tokens

    def record_tool(self, tool_name: str, tool_input: str | None = None) -> None:
        """记录工具调用信息"""
        self._record.tool_name = tool_name
        if tool_input:
            self._record.input_data = tool_input

    def set_risk_level(self, level: str) -> None:
        """设置风险等级"""
        self._record.risk_level = level

    def set_metadata(self, key: str, value: Any) -> None:
        """附加元数据"""
        if self._record.metadata is None:
            self._record.metadata = {}
        self._record.metadata[key] = value


# ============================================================
# 便捷函数
# ============================================================


def _gen_trace_id() -> str:
    """生成唯一 trace_id"""
    return uuid.uuid4().hex


def _gen_span_id() -> str:
    """生成唯一 span_id"""
    return uuid.uuid4().hex[:16]


def start_trace(user_query: str | None = None) -> TraceInfo:
    """
    开始一个新的顶层 trace。

    Args:
        user_query: 用户请求文本（可选）

    Returns:
        TraceInfo 实例
    """
    trace = TraceInfo(trace_id=_gen_trace_id(), span_id=_gen_span_id())
    set_current_trace(trace)
    return trace


def end_trace() -> None:
    """结束当前 trace，清除上下文"""
    set_current_trace(None)


def record_llm_usage(
    agent_name: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float = 0.0,
    input_data: str | None = None,
    output_data: str | None = None,
) -> SpanRecord:
    """
    快速记录一次 LLM 调用。

    Args:
        agent_name: 调用 LLM 的 Agent
        input_tokens: 输入 token 数
        output_tokens: 输出 token 数
        latency_ms: 耗时
        input_data: 输入（截断后的 prompt）
        output_data: 输出（截断后的 completion）

    Returns:
        记录的 SpanRecord
    """
    current = get_current_trace()
    trace_id = current.trace_id if current else _gen_trace_id()
    parent_span_id = current.span_id if current else None

    span = SpanRecord(
        trace_id=trace_id,
        span_id=_gen_span_id(),
        parent_span_id=parent_span_id,
        kind=SpanKind.LLM,
        agent_name=agent_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        input_data=input_data,
        output_data=output_data,
        status=SpanStatus.SUCCESS,
        started_at=time.perf_counter(),
        ended_at=time.perf_counter(),
    )
    get_trace_recorder().record(span)
    return span


def record_tool_call(
    tool_name: str,
    agent_name: str,
    tool_input: str | None = None,
    tool_output: str | None = None,
    latency_ms: float = 0.0,
) -> SpanRecord:
    """
    快速记录一次 MCP 工具调用。

    Args:
        tool_name: 工具名称
        agent_name: 调用方 Agent
        tool_input: 工具输入
        tool_output: 工具输出
        latency_ms: 耗时

    Returns:
        记录的 SpanRecord
    """
    current = get_current_trace()
    trace_id = current.trace_id if current else _gen_trace_id()
    parent_span_id = current.span_id if current else None

    span = SpanRecord(
        trace_id=trace_id,
        span_id=_gen_span_id(),
        parent_span_id=parent_span_id,
        kind=SpanKind.TOOL,
        agent_name=agent_name,
        tool_name=tool_name,
        input_data=tool_input,
        output_data=tool_output,
        latency_ms=latency_ms,
        status=SpanStatus.SUCCESS,
        started_at=time.perf_counter(),
        ended_at=time.perf_counter(),
    )
    get_trace_recorder().record(span)
    return span


# ============================================================
# Smoke Test
# ============================================================

if __name__ == "__main__":
    import asyncio

    passed = 0
    failed = 0

    def check(name: str, actual: Any, expected: Any) -> None:
        global passed, failed
        if actual == expected:
            passed += 1
            print(f"  [OK] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}: expected={expected!r}, got={actual!r}")

    print("=== governance.trace smoke test ===")

    # ── TraceInfo ──
    print("--- TraceInfo ---")
    t1 = TraceInfo(trace_id="abc", span_id="001")
    check("trace_id", t1.trace_id, "abc")
    check("span_id", t1.span_id, "001")
    check("parent_none", t1.parent_span_id, None)

    child = t1.child()
    check("child_trace_id", child.trace_id, "abc")
    check("child_parent", child.parent_span_id, "001")
    check("child_span_diff", child.span_id != "001", True)

    # ── SpanRecord ──
    print("--- SpanRecord ---")
    sr = SpanRecord(
        trace_id="t1", span_id="s1", parent_span_id=None,
        kind=SpanKind.AGENT, agent_name="supervisor",
        input_tokens=100, output_tokens=50, latency_ms=200.0,
        status=SpanStatus.SUCCESS,
    )
    check("sr_trace", sr.trace_id, "t1")
    check("sr_kind", sr.kind, SpanKind.AGENT)
    check("sr_tokens", sr.input_tokens + sr.output_tokens, 150)

    summary = sr.to_summary()
    check("summary_keys", set(summary.keys()),
          {"trace_id", "span_id", "kind", "agent_name", "tool_name", "latency_ms", "token_usage", "status"})

    db_dict = sr.to_db_dict()
    check("db_trace_id", db_dict["trace_id"], "t1")
    check("db_status", db_dict["status"], "success")

    # ── TraceRecorder ──
    print("--- TraceRecorder ---")
    recorder = TraceRecorder()
    check("recorder_empty", len(recorder.spans), 0)

    recorder.record(sr)
    check("recorder_one", len(recorder.spans), 1)

    sr2 = SpanRecord(
        trace_id="t2", span_id="s2", parent_span_id=None,
        kind=SpanKind.TOOL, agent_name="policy", tool_name="search_policy",
        latency_ms=50.0, status=SpanStatus.SUCCESS,
    )
    recorder.record(sr2)
    check("recorder_two", len(recorder.spans), 2)

    t1_spans = recorder.get_spans_by_trace("t1")
    check("filter_trace", len(t1_spans), 1)

    policy_spans = recorder.get_spans_by_agent("policy")
    check("filter_agent", len(policy_spans), 1)

    stats = recorder.get_stats()
    check("stats_spans", stats["total_spans"], 2)
    check("stats_agent", stats["agent_calls"], 1)
    check("stats_tool", stats["tool_calls"], 1)
    check("stats_success", stats["success_count"], 2)

    recorder.clear()
    check("recorder_clear", len(recorder.spans), 0)

    # ── Context propagation ──
    print("--- Context ---")
    trace = start_trace("test query")
    check("context_set", get_current_trace() is not None, True)
    check("context_trace_id", get_current_trace().trace_id == trace.trace_id, True)
    end_trace()
    check("context_clear", get_current_trace(), None)

    # ── record_llm_usage / record_tool_call ──
    print("--- Convenience ---")
    reset_trace_recorder()
    rec = get_trace_recorder()

    llm_span = record_llm_usage(
        agent_name="policy", input_tokens=200, output_tokens=100,
        latency_ms=500.0,
    )
    check("llm_recorded", len(rec.spans), 1)
    check("llm_kind", llm_span.kind, SpanKind.LLM)

    tool_span = record_tool_call(
        tool_name="search_policy", agent_name="policy",
        tool_input='{"query": "test"}', latency_ms=50.0,
    )
    check("tool_recorded", len(rec.spans), 2)
    check("tool_kind", tool_span.kind, SpanKind.TOOL)

    # ── SpanInProgress ──
    print("--- SpanInProgress ---")
    sr3 = SpanRecord(
        trace_id="t3", span_id="s3", parent_span_id=None,
        kind=SpanKind.AGENT, agent_name="workflow",
        status=SpanStatus.RUNNING, started_at=time.perf_counter(),
    )
    sip = SpanInProgress(sr3)
    check("sip_trace", sip.trace_id, "t3")
    sip.record_output("result text")
    sip.record_tokens(50, 25)
    sip.record_tool("create_case", '{"type": "business"}')
    sip.set_risk_level("medium")
    sip.set_metadata("version", "1.0")
    check("sip_output", sr3.output_data, "result text")
    check("sip_in_tokens", sr3.input_tokens, 50)
    check("sip_tool", sr3.tool_name, "create_case")
    check("sip_risk", sr3.risk_level, "medium")
    check("sip_meta", sr3.metadata, {"version": "1.0"})

    # ── AgentTracer sync span ──
    print("--- AgentTracer sync ---")
    reset_trace_recorder()
    rec2 = get_trace_recorder()

    with AgentTracer.span_sync(agent_name="supervisor", kind=SpanKind.AGENT) as span:
        span.record_output("task plan generated")
        span.record_tokens(30, 15)

    check("sync_recorded", len(rec2.spans), 1)
    sync_span = rec2.spans[0]
    check("sync_agent", sync_span.agent_name, "supervisor")
    check("sync_status", sync_span.status, SpanStatus.SUCCESS)
    check("sync_output", sync_span.output_data, "task plan generated")
    check("sync_latency_positive", sync_span.latency_ms > 0, True)

    # ── AgentTracer error handling ──
    print("--- AgentTracer error ---")
    try:
        with AgentTracer.span_sync(agent_name="policy") as span:
            raise ValueError("test error")
    except ValueError:
        pass

    error_span = rec2.spans[-1]
    check("error_span_status", error_span.status, SpanStatus.FAILED)
    check("error_span_msg", "test error" in (error_span.error_message or ""), True)
    check("error_span_risk", error_span.risk_level, "high")
    check("error_context_restored", get_current_trace(), None)

    # ── Nested spans ──
    print("--- Nested spans ---")
    reset_trace_recorder()
    rec3 = get_trace_recorder()

    with AgentTracer.span_sync(agent_name="supervisor", kind=SpanKind.AGENT) as parent_span:
        parent_span.record_output("plan")
        with AgentTracer.span_sync(agent_name="policy", kind=SpanKind.AGENT) as child_span:
            child_span.record_output("policy result")

    check("nested_count", len(rec3.spans), 2)
    # Inner span records first (finally runs before outer)
    inner_span = rec3.spans[0]   # policy (recorded first by inner finally)
    outer_span = rec3.spans[1]   # supervisor (recorded second by outer finally)
    check("nested_same_trace", inner_span.trace_id, outer_span.trace_id)
    check("nested_parent_link", inner_span.parent_span_id, outer_span.span_id)

    # ── Summary ──
    total = passed + failed
    print(f"\n=== {passed}/{total} passed, {failed} failed ===")
    if failed > 0:
        raise SystemExit(1)
