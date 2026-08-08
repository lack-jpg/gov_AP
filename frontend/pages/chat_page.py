"""
frontend.pages.chat_page - 多 Agent 协同对话演示（流式 + 多轮）

通过 FastAPI 后端 /api/chat（或 /api/chat/stream）调用完整 Agent 工作流：
Supervisor → Intent → Policy/Material → Workflow → Governance → 回答
后端不可用时自动降级本地 stub 模式。
"""
from __future__ import annotations

import os
import sys
import uuid

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from frontend.common import setup_paths  # noqa: E402
from frontend import api_client  # noqa: E402
from frontend import ui  # noqa: E402

setup_paths()

# ============================================================
# 会话状态（多轮对话消息 + 会话 ID）
# ============================================================
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "conversation_id" not in st.session_state:
    st.session_state["conversation_id"] = None

# ── 后端状态提示 ──
backend_available = api_client.health() is not None

# ============================================================
# 侧边栏 — 历史会话管理
# ============================================================
with st.sidebar:
    st.subheader("💬 历史会话")
    if backend_available:
        if st.button("＋ 新对话", use_container_width=True):
            st.session_state["conversation_id"] = None
            st.session_state["messages"] = []

        convs = api_client.list_conversations().get("items", [])
        for conv in convs:
            label = (conv.get("title") or conv.get("conversation_id", ""))[:24]
            cid = conv.get("conversation_id")
            if st.button(f"🗂 {label}", key=f"conv_{cid}", use_container_width=True):
                msgs = api_client.get_conversation_messages(cid).get("messages", [])
                st.session_state["conversation_id"] = cid
                st.session_state["messages"] = [
                    {"role": m["role"], "content": m["content"]} for m in msgs
                ]
    else:
        st.info("后端未启动，无历史会话")

# ============================================================
# 页头
# ============================================================
ui.page_header(
    "💬",
    "智能对话",
    "多 Agent 协同处理：**Supervisor → Intent → Policy/Material → Workflow → Governance → 回答**",
)

# ── 示例问题 ──
EXAMPLES = [
    "我想在成都开一家川菜馆，需要什么手续和材料？",
    "查询公积金账户余额需要哪些材料？",
    "办理房产过户需要什么材料？",
    "我要注册一家科技公司，流程是什么？",
    "社保卡怎么办理？",
]

examples = ["✍️ 自定义输入"] + EXAMPLES
selected = st.pills("示例问题", examples, default="✍️ 自定义输入")
query = st.text_area(
    "请输入您的问题",
    value="" if selected == "✍️ 自定义输入" else selected,
    height=80,
    placeholder="例如：我想开一家餐馆，需要什么手续",
)

if not backend_available:
    st.info("💡 后端 API 未启动，对话将使用**本地 stub 模式**（BERT 意图分类 + 政策模板）。启动后端即可切换为完整 Agent 工作流。")

send = st.button("🚀 发送", type="primary", use_container_width=True)


def _render_history() -> None:
    """渲染已有对话消息。"""
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])


_render_history()

# ============================================================
# 发送处理（流式 / stub）
# ============================================================
if send:
    if not query.strip():
        st.warning("请输入问题")
    else:
        # 首次对话生成会话 ID（多轮上下文关联）
        if st.session_state["conversation_id"] is None:
            st.session_state["conversation_id"] = f"conv_{uuid.uuid4().hex[:12]}"
        conversation_id = st.session_state["conversation_id"]

        # 用户消息
        st.session_state["messages"].append({"role": "user", "content": query.strip()})
        with st.chat_message("user"):
            st.markdown(query.strip())

        answer_text = ""
        if backend_available:
            # ── 流式模式：SSE 节点进度 → 最终回答 ──
            status_ph = st.empty()
            final = None
            seen_nodes: set[str] = set()
            for ev in api_client.chat_stream(
                query.strip(), conversation_id=conversation_id,
            ):
                ev_type = ev.get("event")
                if ev_type == "node":
                    label = ev.get("label") or ev.get("node", "")
                    status_ph.info(f"⏳ 正在执行：**{label}** …")
                elif ev_type == "final":
                    final = ev
                    status_ph.empty()
                    break
                elif ev_type == "error":
                    status_ph.empty()
                    st.error(f"❌ {ev.get('message', '流式请求失败')}")
                    break

            with st.chat_message("assistant"):
                if final:
                    answer_text = final.get("answer", "") or "（未生成回答）"
                    st.markdown(answer_text)

                    # ── 结果指标 ──
                    risk = final.get("risk_level", "-")
                    risk_accent = {"low": "green", "medium": "amber", "high": "red", "critical": "red"}.get(risk, "gray")
                    m1, m2, m3, m4 = st.columns(4)
                    with m1:
                        ui.metric_card("🎯 识别意图", final.get("intent", "-"), accent="blue")
                    with m2:
                        ui.metric_card("⚙️ 执行步数", final.get("execution_steps", 0), accent="gray")
                    with m3:
                        ui.metric_card("⏱️ 耗时", f"{final.get('elapsed_ms', 0):.0f} ms", accent="amber")
                    with m4:
                        st.markdown(
                            '<div class="gp-metric">'
                            '<div class="gp-metric-label">🛡️ 风险等级</div>'
                            f'<div style="margin-top:6px;">{ui.status_badge(risk)}</div>'
                            "</div>",
                            unsafe_allow_html=True,
                        )

                    # ── 引用证据 ──
                    evidence = final.get("evidence") or []
                    if evidence:
                        ui.section_header("📚", "引用证据")
                        for ev in evidence:
                            if isinstance(ev, dict):
                                ui.evidence_card(
                                    ev.get("source", "未知来源"),
                                    ev.get("relevance_score", 0),
                                    ev.get("excerpt", ""),
                                )

                    trace_id = final.get("trace_id")
                    if trace_id:
                        st.caption(f"🔍 trace_id: `{trace_id}`")
                else:
                    st.markdown("（未生成回答）")
        else:
            # ── 降级：本地 stub 模式 ──
            with st.chat_message("assistant"):
                with st.spinner("🔄 本地 stub 模式处理中（BERT 分类 + 政策模板）..."):
                    status, data = api_client.chat_with_fallback(query.strip())
                if status == 200:
                    answer_text = data.get("answer", "") or "（未生成回答）"
                    st.markdown(answer_text)
                    if data.get("mode") == "stub":
                        st.caption("💡 本地 stub 模式（后端未启动）")
                    if data.get("trace_id"):
                        st.caption(f"🔍 trace_id: `{data.get('trace_id')}`")
                else:
                    st.error(f"❌ 请求失败: {data.get('error', status)}")

        if answer_text:
            st.session_state["messages"].append({"role": "assistant", "content": answer_text})
