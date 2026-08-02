"""
frontend.pages.7_运维看板 - AgentOps 运维看板

Agent 运行统计（从后端 /api/dashboard/overview）+ 评测报告（/api/evaluation/report）
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import setup_paths  # noqa: E402
import api_client  # noqa: E402

setup_paths()

st.set_page_config(page_title="运维看板", page_icon="📊", layout="wide")
st.title("📊 运维看板（AgentOps）")
st.caption("Agent 运行统计 · 成功率 · 评测报告")

# ============================================================
# 后端连接状态
# ============================================================
if not api_client.health():
    st.warning("⚠️ 后端 API 未启动（http://localhost:8002），看板数据不可用。请先启动服务。")
else:
    st.success("✅ 后端已连接")

st.divider()

# ============================================================
# 运行概览
# ============================================================
st.subheader("📈 运行概览")
overview = api_client.dashboard_overview()

if overview:
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("总请求数", overview.get("total_requests", 0))
    m2.metric("成功率", f"{overview.get('success_rate', 0) * 100:.1f}%")
    m3.metric("平均耗时", f"{overview.get('avg_latency_ms', 0):.0f} ms")
    m4.metric("活跃 Agent", overview.get("active_agents", 0))
    m5.metric("MCP 调用", overview.get("tool_call_count", 0))
    m6.metric("A2A 任务", overview.get("a2a_task_count", 0))

    if overview.get("total_requests", 0) == 0:
        st.info("💡 暂无请求数据。去 **💬 智能对话** 页发起一次对话后，这里会显示真实统计。")
else:
    st.info("暂无运行数据")

st.divider()

# ============================================================
# 评测报告
# ============================================================
st.subheader("🧪 评测报告")
version = st.text_input("评测版本", "v1")

report = api_client.evaluation_report(version)

if report:
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("任务成功率", f"{report.get('task_success_rate', 0) * 100:.1f}%")
    r2.metric("工具准确率", f"{report.get('tool_accuracy', 0) * 100:.1f}%")
    r3.metric("RAG 真实性", f"{report.get('rag_faithfulness', 0) * 100:.1f}%")
    r4.metric("答案相关性", f"{report.get('rag_answer_relevance', 0) * 100:.1f}%")

    r5, r6, r7 = st.columns(3)
    r5.metric("平均耗时", f"{report.get('avg_latency_ms', 0):.0f} ms")
    r6.metric("平均步数", report.get("avg_step_count", 0))
    r7.metric("通过/总用例", f"{report.get('passed_cases', 0)}/{report.get('total_cases', 0)}")

    if report.get("error"):
        st.warning(report["error"])
else:
    st.info(f"版本 `{version}` 暂无评测报告。\n\n运行评测生成报告：`python -m governance.evaluation.runner run --version {version}`")

st.divider()

# ============================================================
# 评测数据集
# ============================================================
st.subheader("🗂️ 评测数据集")
datasets = [
    ("intent_cases", "意图分类", "10 条"),
    ("rag_cases", "RAG 检索", "5 条"),
    ("agent_cases", "多 Agent 任务", "3 条"),
    ("security_cases", "安全治理", "3 条"),
    ("business_license", "营业执照场景", "3 条"),
    ("policy_query", "政策查询", "3 条"),
    ("workflow", "流程执行", "2 条"),
]
for name, desc, count in datasets:
    st.markdown(f"- **`{name}.json`** — {desc}（{count}）")
st.caption("数据集位于 `cases/` 目录，格式兼容 GoldenDataset loader 与评测引擎")
