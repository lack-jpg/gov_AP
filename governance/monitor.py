"""
governance.monitor - Agent monitor: real-time agent health, performance metrics collection

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement agent monitoring with Prometheus metrics export
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ============================================================
# 指标类型
# ============================================================


class MetricType:
    """Prometheus 指标类型常量"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricValue:
    """单个指标值（带标签）"""
    labels: dict[str, str] = field(default_factory=dict)
    value: float = 0.0


@dataclass
class Metric:
    """一个 Prometheus 兼容的指标"""
    name: str
    type: str                    # counter | gauge | histogram | summary
    help: str                    # HELP 描述
    values: list[MetricValue] = field(default_factory=list)

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        """设置 Gauge 值（替换同标签的已有值）"""
        labels = labels or {}
        for mv in self.values:
            if mv.labels == labels:
                mv.value = value
                return
        self.values.append(MetricValue(labels=labels, value=value))

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Counter 增加"""
        labels = labels or {}
        for mv in self.values:
            if mv.labels == labels:
                mv.value += amount
                return
        self.values.append(MetricValue(labels=labels, value=amount))

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        """记录 Histogram 观测值（存储 sum + count + buckets）"""
        labels = labels or {}
        # 对于 histogram，多次观测会更新 sum/count
        sum_key = {**labels, "__stat__": "sum"}
        count_key = {**labels, "__stat__": "count"}

        for mv in self.values:
            if mv.labels == sum_key:
                mv.value += value
                break
        else:
            self.values.append(MetricValue(labels=sum_key, value=value))

        for mv in self.values:
            if mv.labels == count_key:
                mv.value += 1.0
                break
        else:
            self.values.append(MetricValue(labels=count_key, value=1.0))

    def get_value(self, labels: dict[str, str] | None = None) -> float | None:
        """获取指定标签的值"""
        labels = labels or {}
        for mv in self.values:
            if mv.labels == labels:
                return mv.value
        return None

    def to_prometheus_text(self) -> str:
        """转为 Prometheus 文本格式"""
        lines: list[str] = []
        lines.append(f"# HELP {self.name} {self.help}")
        lines.append(f"# TYPE {self.name} {self.type}")
        for mv in self.values:
            if "__stat__" in mv.labels:
                continue  # sum/count 在 histogram 中特殊处理
            label_str = _format_labels(mv.labels)
            if label_str:
                lines.append(f"{self.name}{{{label_str}}} {float(mv.value)}")
            else:
                lines.append(f"{self.name} {float(mv.value)}")

            # Histogram: 附加 sum 和 count
            if self.type == MetricType.HISTOGRAM:
                sum_key = {**mv.labels, "__stat__": "sum"}
                count_key = {**mv.labels, "__stat__": "count"}
                sum_val = next((v.value for v in self.values if v.labels == sum_key), 0.0)
                count_val = next((v.value for v in self.values if v.labels == count_key), 0.0)
                if label_str:
                    lines.append(f"{self.name}_sum{{{label_str}}} {float(sum_val)}")
                    lines.append(f"{self.name}_count{{{label_str}}} {float(count_val)}")
                else:
                    lines.append(f"{self.name}_sum {float(sum_val)}")
                    lines.append(f"{self.name}_count {float(count_val)}")

        return "\n".join(lines)


def _format_labels(labels: dict[str, str]) -> str:
    """格式化 Prometheus label 字符串"""
    if not labels:
        return ""
    return ",".join(
        f'{k}="{v}"' for k, v in sorted(labels.items())
    )


# ============================================================
# MetricsCollector — 指标收集器
# ============================================================


class MetricsCollector:
    """
    Agent 指标收集器 — 收集并暴露 Prometheus 兼容指标。

    用法:
        collector = MetricsCollector()
        collector.record_agent_call("supervisor", success=True, latency_ms=200)
        collector.record_tool_call("search_policy", success=True, latency_ms=50)
        print(collector.export_prometheus())
    """

    def __init__(self) -> None:
        # Agent 调用计数 (counter)
        self._agent_calls_total = Metric(
            name="agent_calls_total",
            type=MetricType.COUNTER,
            help="Total number of agent calls.",
        )
        # Agent 成功计数 (counter)
        self._agent_success_total = Metric(
            name="agent_success_total",
            type=MetricType.COUNTER,
            help="Total number of successful agent calls.",
        )
        # Agent 失败计数 (counter)
        self._agent_failure_total = Metric(
            name="agent_failure_total",
            type=MetricType.COUNTER,
            help="Total number of failed agent calls.",
        )
        # Agent 延迟 (histogram)
        self._agent_latency = Metric(
            name="agent_latency_ms",
            type=MetricType.HISTOGRAM,
            help="Agent call latency in milliseconds.",
        )
        # Agent 当前并发 (gauge)
        self._agent_active = Metric(
            name="agent_active_current",
            type=MetricType.GAUGE,
            help="Number of currently active agent calls.",
        )
        # Agent 步骤数 (histogram)
        self._agent_steps = Metric(
            name="agent_steps_total",
            type=MetricType.HISTOGRAM,
            help="Agent execution step count.",
        )
        # LLM Token 用量 (counter)
        self._llm_tokens_total = Metric(
            name="llm_tokens_total",
            type=MetricType.COUNTER,
            help="Total LLM token usage.",
        )

        # 工具调用计数 (counter)
        self._tool_calls_total = Metric(
            name="tool_calls_total",
            type=MetricType.COUNTER,
            help="Total number of MCP tool calls.",
        )
        # 工具成功计数 (counter)
        self._tool_success_total = Metric(
            name="tool_success_total",
            type=MetricType.COUNTER,
            help="Total number of successful tool calls.",
        )
        # 工具失败计数 (counter)
        self._tool_failure_total = Metric(
            name="tool_failure_total",
            type=MetricType.COUNTER,
            help="Total number of failed tool calls.",
        )
        # 工具延迟 (histogram)
        self._tool_latency = Metric(
            name="tool_latency_ms",
            type=MetricType.HISTOGRAM,
            help="Tool call latency in milliseconds.",
        )

        # Guardrail 阻断计数 (counter)
        self._guardrail_blocks_total = Metric(
            name="guardrail_blocks_total",
            type=MetricType.COUNTER,
            help="Total number of guardrail blocks.",
        )

        # 运行中 span 计数
        self._active_spans: set[str] = set()

        # 历史记录（用于计算 success_rate）
        self._history: list[dict[str, Any]] = []

    # ── 记录方法 ──

    def record_agent_call(
        self,
        agent_name: str,
        success: bool = True,
        latency_ms: float = 0.0,
        step_count: int = 1,
        input_tokens: int = 0,
        output_tokens: int = 0,
        trace_id: str | None = None,
    ) -> None:
        """
        记录一次 Agent 调用。

        Args:
            agent_name: Agent 名称
            success: 是否成功
            latency_ms: 耗时（毫秒）
            step_count: 执行步数
            input_tokens: LLM 输入 token
            output_tokens: LLM 输出 token
            trace_id: 追踪 ID
        """
        labels = {"agent": agent_name}

        self._agent_calls_total.inc(1, labels)
        if success:
            self._agent_success_total.inc(1, labels)
        else:
            self._agent_failure_total.inc(1, labels)

        self._agent_latency.observe(latency_ms, labels)
        self._agent_steps.observe(float(step_count), labels)

        if input_tokens > 0:
            self._llm_tokens_total.inc(float(input_tokens), {**labels, "type": "input"})
        if output_tokens > 0:
            self._llm_tokens_total.inc(float(output_tokens), {**labels, "type": "output"})

        self._history.append({
            "type": "agent",
            "agent_name": agent_name,
            "success": success,
            "latency_ms": latency_ms,
            "step_count": step_count,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def record_tool_call(
        self,
        tool_name: str,
        agent_name: str,
        success: bool = True,
        latency_ms: float = 0.0,
    ) -> None:
        """
        记录一次 MCP 工具调用。

        Args:
            tool_name: 工具名称
            agent_name: 调用方 Agent
            success: 是否成功
            latency_ms: 耗时（毫秒）
        """
        labels = {"tool": tool_name, "agent": agent_name}

        self._tool_calls_total.inc(1, labels)
        if success:
            self._tool_success_total.inc(1, labels)
        else:
            self._tool_failure_total.inc(1, labels)

        self._tool_latency.observe(latency_ms, labels)

        self._history.append({
            "type": "tool",
            "tool_name": tool_name,
            "agent_name": agent_name,
            "success": success,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def record_guardrail_block(
        self,
        guard_type: str,
        severity: str = "medium",
    ) -> None:
        """
        记录一次护栏阻断。

        Args:
            guard_type: 护栏类型
            severity: 严重等级
        """
        self._guardrail_blocks_total.inc(1, {"type": guard_type, "severity": severity})

    def start_span(self, span_id: str) -> None:
        """标记一个 span 开始执行（并发计数+1）"""
        self._active_spans.add(span_id)
        self._agent_active.set(float(len(self._active_spans)))

    def end_span(self, span_id: str) -> None:
        """标记一个 span 结束执行（并发计数-1）"""
        self._active_spans.discard(span_id)
        self._agent_active.set(float(len(self._active_spans)))

    # ── 查询方法 ──

    def get_agent_success_rate(
        self, agent_name: str | None = None
    ) -> float:
        """
        获取 Agent 成功率。

        Args:
            agent_name: 可选，按 agent 过滤

        Returns:
            成功率 (0.0~1.0)，无记录时返回 0.0
        """
        labels = {"agent": agent_name} if agent_name else {}
        total = self._agent_calls_total.get_value(labels) or 0.0
        if total == 0:
            return 0.0
        success = self._agent_success_total.get_value(labels) or 0.0
        return success / total

    def get_tool_success_rate(
        self, tool_name: str | None = None
    ) -> float:
        """
        获取工具调用成功率。

        Args:
            tool_name: 可选，按 tool 过滤

        Returns:
            成功率 (0.0~1.0)
        """
        if tool_name:
            # 遍历所有 tool 的 labels 找到匹配的
            total = 0.0
            success = 0.0
            for mv in self._tool_calls_total.values:
                if mv.labels.get("tool") == tool_name:
                    total += mv.value
            for mv in self._tool_success_total.values:
                if mv.labels.get("tool") == tool_name:
                    success += mv.value
        else:
            total = sum(mv.value for mv in self._tool_calls_total.values)
            success = sum(mv.value for mv in self._tool_success_total.values)

        if total == 0:
            return 0.0
        return success / total

    def get_avg_latency_ms(
        self, agent_name: str | None = None
    ) -> float:
        """
        获取平均延迟。

        Args:
            agent_name: 可选，按 agent 过滤

        Returns:
            平均延迟（毫秒）
        """
        labels = {"agent": agent_name} if agent_name else {}
        sum_val = 0.0
        count_val = 0.0
        for mv in self._agent_latency.values:
            if mv.labels.get("__stat__") == "sum":
                if not agent_name or mv.labels.get("agent") == agent_name:
                    sum_val += mv.value
            elif mv.labels.get("__stat__") == "count":
                if not agent_name or mv.labels.get("agent") == agent_name:
                    count_val += mv.value

        if count_val == 0:
            return 0.0
        return sum_val / count_val

    def get_stats(self) -> dict[str, Any]:
        """
        获取完整统计摘要。

        Returns:
            统计数据字典
        """
        total_calls = sum(mv.value for mv in self._agent_calls_total.values)
        total_success = sum(mv.value for mv in self._agent_success_total.values)
        total_tool_calls = sum(mv.value for mv in self._tool_calls_total.values)
        total_tokens = sum(mv.value for mv in self._llm_tokens_total.values)

        # Per-agent stats
        per_agent: dict[str, dict[str, Any]] = {}
        for mv in self._agent_calls_total.values:
            agent = mv.labels.get("agent", "unknown")
            if agent not in per_agent:
                per_agent[agent] = {
                    "calls": 0, "success": 0, "failure": 0,
                    "success_rate": 0.0, "avg_latency_ms": 0.0,
                }
            per_agent[agent]["calls"] = int(mv.value)
            per_agent[agent]["success"] = int(
                self._agent_success_total.get_value({"agent": agent}) or 0
            )
            per_agent[agent]["failure"] = int(
                self._agent_failure_total.get_value({"agent": agent}) or 0
            )
            per_agent[agent]["success_rate"] = self.get_agent_success_rate(agent)
            per_agent[agent]["avg_latency_ms"] = round(
                self.get_avg_latency_ms(agent), 2
            )

        return {
            "agent": {
                "total_calls": int(total_calls),
                "total_success": int(total_success),
                "total_failure": int(total_calls - total_success),
                "overall_success_rate": round(
                    (total_success / total_calls) if total_calls > 0 else 0.0, 4
                ),
                "per_agent": per_agent,
                "active_spans": len(self._active_spans),
            },
            "tool": {
                "total_calls": int(total_tool_calls),
                "total_success": int(sum(mv.value for mv in self._tool_success_total.values)),
                "total_failure": int(sum(mv.value for mv in self._tool_failure_total.values)),
            },
            "llm": {
                "total_tokens": int(total_tokens),
            },
            "guardrail": {
                "total_blocks": int(sum(mv.value for mv in self._guardrail_blocks_total.values)),
            },
        }

    def get_all_metrics(self) -> list[Metric]:
        """返回所有已注册的 Metric 对象"""
        return [
            self._agent_calls_total,
            self._agent_success_total,
            self._agent_failure_total,
            self._agent_latency,
            self._agent_active,
            self._agent_steps,
            self._llm_tokens_total,
            self._tool_calls_total,
            self._tool_success_total,
            self._tool_failure_total,
            self._tool_latency,
            self._guardrail_blocks_total,
        ]

    def export_prometheus(self) -> str:
        """
        将所有指标导出为 Prometheus 文本格式。

        Returns:
            Prometheus exposition 文本
        """
        lines: list[str] = []
        for metric in self.get_all_metrics():
            text = metric.to_prometheus_text()
            if text.strip():
                lines.append(text)
                lines.append("")  # 空行分隔
        return "\n".join(lines).strip()

    def clear(self) -> None:
        """重置所有指标（测试用）"""
        self.__init__()


# ============================================================
# 全局单例
# ============================================================


_collector: MetricsCollector | None = None


def get_collector() -> MetricsCollector:
    """获取全局 MetricsCollector 单例"""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def reset_collector() -> None:
    """重置全局 MetricsCollector"""
    global _collector
    _collector = MetricsCollector()


# ============================================================
# 便捷函数
# ============================================================


def record_agent_call(
    agent_name: str,
    success: bool = True,
    latency_ms: float = 0.0,
    step_count: int = 1,
    input_tokens: int = 0,
    output_tokens: int = 0,
    trace_id: str | None = None,
) -> None:
    """快速记录 Agent 调用（使用全局 collector）"""
    get_collector().record_agent_call(
        agent_name=agent_name,
        success=success,
        latency_ms=latency_ms,
        step_count=step_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        trace_id=trace_id,
    )


def record_tool_call(
    tool_name: str,
    agent_name: str,
    success: bool = True,
    latency_ms: float = 0.0,
) -> None:
    """快速记录工具调用（使用全局 collector）"""
    get_collector().record_tool_call(
        tool_name=tool_name,
        agent_name=agent_name,
        success=success,
        latency_ms=latency_ms,
    )


def get_metrics_snapshot() -> dict[str, Any]:
    """获取当前指标快照"""
    return get_collector().get_stats()


def export_prometheus_metrics() -> str:
    """导出 Prometheus 格式指标文本"""
    return get_collector().export_prometheus()


# ============================================================
# Smoke Test
# ============================================================

if __name__ == "__main__":
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

    def check_approx(name: str, actual: float, expected: float, tolerance: float = 0.01) -> None:
        global passed, failed
        if abs(actual - expected) <= tolerance:
            passed += 1
            print(f"  [OK] {name} (~{expected})")
        else:
            failed += 1
            print(f"  [FAIL] {name}: expected~{expected!r}, got={actual!r}")

    print("=== governance.monitor smoke test ===")

    # ── Metric basics ──
    print("--- Metric ---")
    m = Metric(name="test_counter", type=MetricType.COUNTER, help="Test counter.")
    check("metric_name", m.name, "test_counter")
    check("metric_type", m.type, MetricType.COUNTER)
    check("metric_empty", len(m.values), 0)

    m.inc(1, {"agent": "supervisor"})
    check("metric_inc", m.get_value({"agent": "supervisor"}), 1.0)

    m.inc(2, {"agent": "supervisor"})
    check("metric_inc2", m.get_value({"agent": "supervisor"}), 3.0)

    m.inc(1, {"agent": "policy"})
    check("metric_second_label", m.get_value({"agent": "policy"}), 1.0)

    # Gauge
    g = Metric(name="test_gauge", type=MetricType.GAUGE, help="Test gauge.")
    g.set(5.0, {"agent": "supervisor"})
    check("gauge_set", g.get_value({"agent": "supervisor"}), 5.0)
    g.set(3.0, {"agent": "supervisor"})
    check("gauge_overwrite", g.get_value({"agent": "supervisor"}), 3.0)

    # Histogram
    h = Metric(name="test_histogram", type=MetricType.HISTOGRAM, help="Test histogram.")
    h.observe(100.0, {"agent": "supervisor"})
    h.observe(200.0, {"agent": "supervisor"})

    sum_val = h.get_value({"agent": "supervisor", "__stat__": "sum"})
    count_val = h.get_value({"agent": "supervisor", "__stat__": "count"})
    check("hist_sum", sum_val, 300.0)
    check("hist_count", count_val, 2.0)

    # ── Prometheus text ──
    print("--- Prometheus text ---")
    text = m.to_prometheus_text()
    check("prom_has_help", "# HELP test_counter" in text, True)
    check("prom_has_type", "# TYPE test_counter counter" in text, True)
    check("prom_has_value", 'test_counter{agent="supervisor"}' in text, True)
    check("prom_has_value_policy", 'test_counter{agent="policy"}' in text, True)

    # ── MetricsCollector ──
    print("--- MetricsCollector ---")
    collector = MetricsCollector()

    # Record agent calls
    collector.record_agent_call("supervisor", success=True, latency_ms=200, step_count=2, input_tokens=100, output_tokens=50)
    collector.record_agent_call("supervisor", success=True, latency_ms=300, step_count=1, input_tokens=150, output_tokens=80)
    collector.record_agent_call("policy", success=False, latency_ms=500, step_count=3, input_tokens=200, output_tokens=0)
    collector.record_agent_call("policy", success=True, latency_ms=150, step_count=1, input_tokens=50, output_tokens=30)

    # Record tool calls
    collector.record_tool_call("search_policy", "policy", success=True, latency_ms=50)
    collector.record_tool_call("search_policy", "policy", success=False, latency_ms=100)
    collector.record_tool_call("extract_entity", "material", success=True, latency_ms=30)

    # Record guardrail block
    collector.record_guardrail_block("injection", "high")

    # ── Success rates ──
    print("--- Success rates ---")
    check_approx("supervisor_rate", collector.get_agent_success_rate("supervisor"), 1.0)
    check_approx("policy_rate", collector.get_agent_success_rate("policy"), 0.5)
    check_approx("material_rate", collector.get_agent_success_rate("material"), 0.0)

    tool_rate = collector.get_tool_success_rate("search_policy")
    check_approx("tool_rate", tool_rate, 0.5)

    # ── Avg latency ──
    print("--- Avg latency ---")
    avg = collector.get_avg_latency_ms("supervisor")
    check("avg_latency_supervisor", avg, 250.0)  # (200+300)/2

    avg_policy = collector.get_avg_latency_ms("policy")
    check("avg_latency_policy", avg_policy, 325.0)  # (500+150)/2

    # ── Stats ──
    print("--- Stats ---")
    stats = collector.get_stats()
    check("stats_agent_calls", stats["agent"]["total_calls"], 4)
    check("stats_agent_success", stats["agent"]["total_success"], 3)
    check("stats_tool_calls", stats["tool"]["total_calls"], 3)
    check("stats_llm_tokens", stats["llm"]["total_tokens"], 660)   # 100+50+150+80+200+0+50+30
    check("stats_blocks", stats["guardrail"]["total_blocks"], 1)

    # ── Concurrency ──
    print("--- Concurrency ---")
    collector.start_span("span_1")
    check("active_1", len(collector._active_spans), 1)
    collector.start_span("span_2")
    check("active_2", len(collector._active_spans), 2)
    active_gauge = collector._agent_active.get_value()
    check("gauge_active", active_gauge, 2.0)
    collector.end_span("span_1")
    check("active_after_end", len(collector._active_spans), 1)
    collector.end_span("span_2")
    check("active_all_end", len(collector._active_spans), 0)

    # ── Prometheus export ──
    print("--- Export ---")
    prom_text = collector.export_prometheus()
    check("export_has_agent_calls", "agent_calls_total" in prom_text, True)
    check("export_has_tool_calls", "tool_calls_total" in prom_text, True)
    check("export_has_llm", "llm_tokens_total" in prom_text, True)
    check("export_has_guardrail", "guardrail_blocks_total" in prom_text, True)
    check("export_has_active", "agent_active_current" in prom_text, True)

    # ── Global singleton ──
    print("--- Singleton ---")
    reset_collector()
    c = get_collector()
    check("singleton_not_none", c is not None, True)
    check("singleton_empty", sum(mv.value for mv in c._agent_calls_total.values), 0.0)

    # ── Convenience functions ──
    print("--- Convenience ---")
    reset_collector()
    record_agent_call("test_agent", success=True, latency_ms=100)
    record_tool_call("test_tool", "test_agent", success=True, latency_ms=10)
    snapshot = get_metrics_snapshot()
    check("conv_agent_calls", snapshot["agent"]["total_calls"], 1)
    check("conv_tool_calls", snapshot["tool"]["total_calls"], 1)

    prom = export_prometheus_metrics()
    check("conv_prom_non_empty", len(prom) > 0, True)

    # ── Summary ──
    total = passed + failed
    print(f"\n=== {passed}/{total} passed, {failed} failed ===")
    if failed > 0:
        raise SystemExit(1)
