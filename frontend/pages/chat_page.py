"""
frontend.pages.chat_page - 多 Agent 协同对话演示

通过 FastAPI 后端 /api/chat 调用完整 Agent 工作流：
Supervisor → Intent → Policy/Material → Workflow → Governance → 回答
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import setup_paths  # noqa: E402
import api_client  # noqa: E402

setup_paths()


st.title("💬 智能对话")
st.caption("多 Agent 协同处理：**Supervisor → Intent → Policy/Material → Workflow → Governance → 回答**")

# ── 示例问题 ──
EXAMPLES = [
    "我想在成都开一家川菜馆，需要什么手续和材料？",
    "查询公积金账户余额需要哪些材料？",
    "办理房产过户需要什么材料？",
    "我要注册一家科技公司，流程是什么？",
    "社保卡怎么办理？",
]

selected = st.selectbox("选择示例问题", ["✍️ 自定义输入"] + EXAMPLES)
query = st.text_area(
    "请输入您的问题",
    value="" if selected == "✍️ 自定义输入" else selected,
    height=80,
    placeholder="例如：我想开一家餐馆，需要什么手续",
)

# ── 后端状态提示 ──
backend_available = api_client.health() is not None
if not backend_available:
    st.info("💡 后端 API 未启动，对话将使用**本地 stub 模式**（BERT 意图分类 + 政策模板）。启动后端即可切换为完整 Agent 工作流。")

send = st.button("🚀 发送", type="primary", use_container_width=True)

if send:
    if not query.strip():
        st.warning("请输入问题")
    else:
        if backend_available:
            spinner_text = "🔄 多 Agent 协同处理中（真实 LLM + MCP，可能需要 30~90 秒）..."
        else:
            spinner_text = "🔄 本地 stub 模式处理中（BERT 分类 + 政策模板）..."

        with st.spinner(spinner_text):
            status, data = api_client.chat_with_fallback(query)

        if status == 200:
            is_stub = data.get("mode") == "stub"

            if is_stub:
                st.success("✅ 处理完成（本地 stub 模式）")
                st.caption("💡 当前为本地演示模式，回答基于内置政策模板。启动后端即可使用完整 Agent 工作流（LLM + RAG + MCP）。")
            else:
                st.success("✅ 处理完成")

            st.markdown("### 📝 回答")
            st.markdown(data.get("answer", "") or "（未生成回答）")

            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            intent = data.get("intent", "-")
            risk = data.get("risk_level", "-")
            risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "⛔"}.get(risk, "⚪")
            m1.metric("🎯 识别意图", intent)
            m2.metric("🛡️ 风险等级", f"{risk_icon} {risk}")
            m3.metric("⚙️ 执行步数", data.get("execution_steps", 0))
            m4.metric("⏱️ 耗时", f"{data.get('elapsed_ms', 0):.0f} ms")

            evidence = data.get("evidence") or []
            if evidence:
                st.subheader("📚 引用证据")
                for ev in evidence:
                    with st.container(border=True):
                        st.markdown(f"**{ev.get('source', '未知来源')}**  ·  相关度 {ev.get('relevance_score', 0):.2f}")
                        st.caption(ev.get("excerpt", ""))

            trace_id = data.get("trace_id")
            if trace_id:
                mode_tag = " [stub]" if is_stub else ""
                st.caption(f"🔍 trace_id: `{trace_id}`{mode_tag}")
        else:
            st.error(f"❌ 请求失败: {data.get('error', status)}")
            if status == 0:
                st.info("提示：请确认后端已启动（`docker compose up -d` 或 `uvicorn backend.main:app --port 8002`）")
