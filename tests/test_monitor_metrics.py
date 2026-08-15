"""
P2-2 指标标准化测试。

验证：
1. histogram 输出 _bucket（le 标签）/_sum/_count，累计桶计数正确；
2. 标准指标集（请求/缓存/内存水位）均在 Prometheus 导出中出现；
3. record_request / record_cache_* / update_memory_gauges 正确更新指标；
4. MCP 工具调用指标按当前 Agent 归属记录。
"""
from __future__ import annotations

from governance.monitor import (
    Metric,
    MetricType,
    get_collector,
    reset_collector,
)


def test_histogram_emits_buckets():
    """histogram 应输出 _bucket{le=...}/_sum/_count 样本行，桶为累计计数。"""
    m = Metric(
        name="agent_latency_ms",
        type=MetricType.HISTOGRAM,
        help="latency",
        buckets=[100, 500, 1000],
    )
    m.observe(50.0, {"agent": "policy"})
    m.observe(300.0, {"agent": "policy"})
    m.observe(2000.0, {"agent": "policy"})

    text = m.to_prometheus_text()

    # le=100 只有 50ms 命中；le=500 命中 50+300；le=1000 命中 50+300
    assert 'agent_latency_ms_bucket{agent="policy",le="100"} 1.0' in text
    assert 'agent_latency_ms_bucket{agent="policy",le="500"} 2.0' in text
    assert 'agent_latency_ms_bucket{agent="policy",le="1000"} 2.0' in text
    # +Inf = count
    assert 'agent_latency_ms_bucket{agent="policy",le="+Inf"} 3.0' in text
    assert 'agent_latency_ms_sum{agent="policy"} 2350.0' in text
    assert 'agent_latency_ms_count{agent="policy"} 3.0' in text


def test_standard_metric_set_present():
    """请求/缓存/内存水位等标准指标均应导出。"""
    reset_collector()
    c = get_collector()
    c.record_request("POST", "/api/chat", 200, 123.4)
    c.record_cache_hit()
    c.record_cache_miss()

    text = c.export_prometheus()

    for name in (
        "http_requests_total",
        "http_request_duration_ms",
        "llm_cache_hits_total",
        "llm_cache_misses_total",
        "process_rss_bytes",
        "gov_trace_spans_in_memory",
    ):
        assert name in text, f"缺少指标 {name}"

    # 请求计数带 method/path/status 标签
    assert (
        'http_requests_total{method="POST",path="/api/chat",status="200"} 1.0'
        in text
    )
    # 请求耗时 histogram 含 bucket
    assert 'http_request_duration_ms_bucket{' in text


def test_cache_and_memory_gauges():
    """缓存命中/未命中计数 + 内存水位 gauge 更新。"""
    reset_collector()
    c = get_collector()

    c.record_cache_hit()
    c.record_cache_hit()
    c.record_cache_miss()

    assert c._llm_cache_hits_total.get_value() == 2.0
    assert c._llm_cache_misses_total.get_value() == 1.0

    c.update_memory_gauges()
    rss = c._process_rss_bytes.get_value()
    assert rss is not None and rss > 0  # psutil 读到的进程 RSS 恒为正
    spans = c._trace_spans_gauge.get_value()
    assert spans is not None and spans >= 0


def test_record_tool_metric_with_agent(monkeypatch):
    """MCP 工具调用指标按当前 trace 上下文 Agent 归属记录。"""
    from governance.trace import set_current_agent_name
    from tools.mcp.client import _record_tool_metric

    reset_collector()
    set_current_agent_name("policy")
    _record_tool_metric("search_policy", success=True, latency_ms=50.0)

    stats = get_collector().get_stats()
    assert stats["tool"]["total_calls"] == 1
    assert stats["tool"]["total_success"] == 1
