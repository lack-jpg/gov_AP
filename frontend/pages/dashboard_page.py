"""
frontend.pages.dashboard_page - AgentOps 运维看板

Agent 运行统计（从后端 /api/dashboard/overview）+ 评测报告（/api/evaluation/report）
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from frontend.common import setup_paths  # noqa: E402
from frontend import api_client  # noqa: E402
from frontend import ui  # noqa: E402

setup_paths()

# ============================================================
# 页头
# ============================================================
ui.page_header("📊", "运维看板（AgentOps）", "Agent 运行统计 · 成功率 · 评测报告")

# ── 后端连接状态 ──
if not api_client.health():
    ui.status_card(False, "后端 API 未启动", "看板数据不可用（http://localhost:8002）。请先启动服务。")
else:
    ui.status_card(True, "后端已连接")

# ============================================================
# 运行概览
# ============================================================
ui.section_header("📈", "运行概览")
overview = api_client.dashboard_overview()

if overview:
    metric_specs = [
        ("总请求数", overview.get("total_requests", 0), "blue"),
        ("成功率", f"{overview.get('success_rate', 0) * 100:.1f}%", "green"),
        ("平均耗时", f"{overview.get('avg_latency_ms', 0):.0f} ms", "amber"),
        ("活跃 Agent", overview.get("active_agents", 0), "blue"),
        ("Token 用量", f"{overview.get('total_tokens', 0):,}", "gray"),
        ("A2A 任务", overview.get("a2a_task_count", 0), "blue"),
    ]
    cols = st.columns(6)
    for col, (label, value, accent) in zip(cols, metric_specs):
        with col:
            ui.metric_card(label, value, accent=accent)

    if overview.get("total_requests", 0) == 0:
        st.info("💡 暂无请求数据。去 **💬 智能对话** 页发起一次对话后，这里会显示真实统计。")

    # ── Agent 统计图表（streamlit 原生，零新增依赖） ──
    agent_stats = overview.get("agent_stats") or []
    if agent_stats:
        ui.section_header("🤖", "Agent 统计")
        names = [a.get("agent_name", "") for a in agent_stats]
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("调用次数")
            st.bar_chart({n: a.get("total_calls", 0) for n, a in zip(names, agent_stats)})
            st.subheader("成功率 (%)")
            st.bar_chart({n: round(a.get("success_rate", 0) * 100, 1) for n, a in zip(names, agent_stats)})
        with c2:
            st.subheader("平均耗时 (ms)")
            st.bar_chart({n: round(a.get("avg_latency_ms", 0), 1) for n, a in zip(names, agent_stats)})
            st.subheader("Token 用量")
            st.bar_chart({n: a.get("total_tokens", 0) for n, a in zip(names, agent_stats)})

    # ── 评测趋势（折线） ──
    eval_trends = overview.get("eval_trends") or []
    if eval_trends:
        ui.section_header("📈", "评测趋势")
        st.line_chart({
            t.get("date", ""): round(t.get("task_success_rate", 0) * 100, 1) for t in eval_trends
        })
else:
    ui.empty_state("📭", "暂无运行数据", "启动后端并产生请求后，这里会显示真实统计。")

# ============================================================
# 评测报告
# ============================================================
ui.section_header("🧪", "评测报告")
version = st.text_input("评测版本", "v1")

report = api_client.evaluation_report(version)

if report:
    cols1 = st.columns(4)
    for col, (label, value, accent) in zip(cols1, [
        ("任务成功率", f"{report.get('task_success_rate', 0) * 100:.1f}%", "green"),
        ("工具准确率", f"{report.get('tool_accuracy', 0) * 100:.1f}%", "blue"),
        ("RAG 真实性", f"{report.get('rag_faithfulness', 0) * 100:.1f}%", "green"),
        ("答案相关性", f"{report.get('rag_answer_relevance', 0) * 100:.1f}%", "blue"),
    ]):
        with col:
            ui.metric_card(label, value, accent=accent)

    cols2 = st.columns(3)
    for col, (label, value, accent) in zip(cols2, [
        ("平均耗时", f"{report.get('avg_latency_ms', 0):.0f} ms", "amber"),
        ("平均步数", report.get("avg_step_count", 0), "gray"),
        ("通过/总用例", f"{report.get('passed_cases', 0)}/{report.get('total_cases', 0)}", "green"),
    ]):
        with col:
            ui.metric_card(label, value, accent=accent)

    if report.get("error"):
        st.warning(report["error"])

    # 评分分布柱状图
    st.subheader("评分分布 (%)")
    st.bar_chart({
        "任务成功率": report.get("task_success_rate", 0) * 100,
        "工具准确率": report.get("tool_accuracy", 0) * 100,
        "RAG真实性": report.get("rag_faithfulness", 0) * 100,
        "答案相关性": report.get("rag_answer_relevance", 0) * 100,
    })
else:
    st.info(f"版本 `{version}` 暂无评测报告。\n\n运行评测生成报告：`python -m governance.evaluation.runner run --version {version}`")

# ============================================================
# 评测数据集
# ============================================================
ui.section_header("🗂️", "评测数据集")

# 从 cases/ 目录动态读取实际用例数量
import json as _json
import os as _os

_cases_dir = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "cases",
)
_dataset_meta = [
    ("intent_cases", "意图分类"),
    ("rag_cases", "RAG 检索"),
    ("agent_cases", "多 Agent 任务"),
    ("security_cases", "安全治理"),
    ("business_license", "营业执照场景"),
    ("policy_query", "政策查询"),
    ("workflow", "流程执行"),
]

dataset_loaded = 0
for i in range(0, len(_dataset_meta), 2):
    row = _dataset_meta[i : i + 2]
    cols = st.columns(2)
    for col, (name, desc) in zip(cols, row):
        filepath = _os.path.join(_cases_dir, f"{name}.json")
        count_str = "?"
        try:
            if _os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                # cases/ JSON 结构兼容：顶层可能是 list（如 [{_description, cases, ...}]）
                # 也可能是直接 dict（如 {"cases": [...]}）
                if isinstance(data, list):
                    all_cases: list = []
                    for item in data:
                        if isinstance(item, dict):
                            all_cases.extend(item.get("cases", []))
                    count_val = len(all_cases)
                elif isinstance(data, dict):
                    cases = data.get("cases", [])
                    count_val = len(cases) if isinstance(cases, list) else data.get("_count", data.get("case_count", "?"))
                else:
                    count_val = "?"
                count_str = f"{count_val} 条"
                dataset_loaded += 1
        except Exception:
            count_str = "读取失败"
        with col:
            with st.container(border=True):
                st.markdown(f"**`{name}.json`**  {ui.pill(desc, 'blue')}", unsafe_allow_html=True)
                st.caption(f"{count_str}")

if dataset_loaded > 0:
    st.caption(f"数据集位于 `cases/` 目录，格式兼容 GoldenDataset loader 与评测引擎（已加载 {dataset_loaded}/{len(_dataset_meta)} 个）")
else:
    st.caption("数据集位于 `cases/` 目录，格式兼容 GoldenDataset loader 与评测引擎")
