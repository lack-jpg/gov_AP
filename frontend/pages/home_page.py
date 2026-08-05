"""
frontend.pages.home_page - 政务多智能体协同与治理平台 — 首页总览

系统健康状态、架构展示、平台能力一览
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from frontend.common import setup_paths  # noqa: E402

setup_paths()
from frontend import api_client  # noqa: E402

# ============================================================
# 头部
# ============================================================
st.title("🏛️ 政务多智能体协同与治理平台")
st.caption("Government Agent Platform — LangGraph · MCP · A2A · AgentOps · RAG")
st.divider()

# ============================================================
# 系统健康
# ============================================================
st.subheader("🩺 系统健康")

health = api_client.health()
col_h1, col_h2 = st.columns(2)
with col_h1:
    if health:
        st.success(f"✅ API 服务正常 — {health.get('app')} **v{health.get('version')}**")
    else:
        st.warning("⚠️ API 服务未启动（http://localhost:8002）\n\n"
                   "请运行 `docker compose up -d` 或 `uvicorn backend.main:app --port 8002`")

overview = api_client.dashboard_overview()
if overview:
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("总请求数", overview.get("total_requests", 0))
    m2.metric("成功率", f"{overview.get('success_rate', 0) * 100:.1f}%")
    m3.metric("平均耗时", f"{overview.get('avg_latency_ms', 0):.0f} ms")
    m4.metric("活跃 Agent", overview.get("active_agents", 0))
    m5.metric("MCP 调用", overview.get("tool_call_count", 0))

st.divider()

# ============================================================
# 架构展示
# ============================================================
st.subheader("🧠 系统架构")
st.markdown("**一条请求的旅程：** `用户请求 → 任务理解 → 多Agent协作 → 工具调用 → 流程执行 → 结果评估 → 持续优化`")

st.markdown(
    """
```
                    ┌──────────────────────┐
                    │   FastAPI Gateway     │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  Supervisor Agent     │  (LangGraph StateGraph)
                    │  任务拆解 / Agent路由  │
                    └──────────┬───────────┘
                               ▼
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        ┌───────────┐   ┌───────────┐   ┌────────────┐
        │ Intent    │   │ Policy    │   │ Material   │
        │ Agent     │   │ Agent     │   │ Agent      │
        │ 意图识别   │   │ RAG检索    │   │ 材料审核    │
        └───────────┘   └───────────┘   └────────────┘
              └────────────────┬────────────────┘
                               ▼
                    ┌──────────────────────┐
                    │   Workflow Agent      │  →  A2A 跨域协同
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │   Governance Agent    │  安全护栏 / PII / 风险
                    └──────────┬───────────┘
                               ▼
                           回答用户
"""
)
st.divider()

# ============================================================
# 平台能力
# ============================================================
st.subheader("🚀 平台能力一览")

capabilities = [
    ("💬", "智能对话", "多 Agent 协同回答", "Supervisor → Intent → Policy/Material → Workflow → Governance", "智能对话"),
    ("🎯", "意图识别", "三级分类链", "BERT 模型 → 关键词匹配 → LLM 兜底，输出标签+置信度", "意图识别"),
    ("📚", "政策检索", "RAG 混合检索", "Milvus 向量检索 + BM25 稀疏检索 + Reranker 精排 + LLM 生成", "政策检索"),
    ("📋", "材料审核", "规则校验", "按业务类型校验材料完整性，别名匹配 + 温馨提示", "材料审核"),
    ("🤝", "跨域协同", "A2A 外部 Agent", "通过 A2A 协议调用不动产/公积金等外部系统", "跨域协同"),
    ("🛡️", "安全治理", "Guardrail 护栏", "PII 脱敏、Prompt 注入检测、敏感词过滤、输出安全", "安全治理"),
    ("📊", "运维看板", "AgentOps 监控", "Agent 运行统计、执行成功率、评测报告", "运维看板"),
]

for icon, name, tag, desc, page in capabilities:
    with st.container(border=True):
        c1, c2 = st.columns([1, 6])
        c1.markdown(f"### {icon}")
        c2.markdown(f"**{name}**  ·  `{tag}`")
        c2.caption(desc)
        c2.caption(f"👉 前往侧边栏 **{page}** 体验")

st.divider()
st.caption("🔧 技术栈: Python 3.12 · FastAPI · LangGraph · MCP · A2A · PostgreSQL 16 · Redis 7 · Milvus 2.5")
