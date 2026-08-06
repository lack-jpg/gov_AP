"""
frontend.pages.policy_page - RAG 政策检索演示

检索管线：Milvus 向量检索 + BM25 稀疏检索 + Reranker 精排 + LLM 生成
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from frontend.common import setup_paths, run_async  # noqa: E402
from frontend import ui  # noqa: E402

setup_paths()

try:
    from agents.policy.agent import PolicyAgent  # noqa: E402
    _HAS_LOCAL_MODULES = True
except ImportError:
    PolicyAgent = None  # type: ignore[assignment]
    _HAS_LOCAL_MODULES = False

# ============================================================
# 页头
# ============================================================
ui.page_header(
    "📚",
    "政策检索（RAG）",
    "检索管线：**Embedding(Milvus) + BM25 稀疏检索 → Reranker 精排 → LLM 生成回答**",
)

if not _HAS_LOCAL_MODULES:
    st.warning(
        "⚠️ 此功能依赖项目本地模块（`agents/policy/`），当前 Docker 容器中未包含。\n\n"
        "请本地运行以获得完整体验：\n"
        "```bash\n"
        "pip install -r requirements/requirements.txt\n"
        "streamlit run frontend/app.py\n"
        "```\n\n"
        "💡 提示：Docker 中可使用 **智能对话** 页通过后端 API 进行政策问答。"
    )

EXAMPLES = [
    "开办餐馆需要办理哪些证照？",
    "小微企业有哪些税收优惠政策？",
    "公积金贷款利率是多少？",
    "企业注册需要哪些材料？",
]

examples = ["✍️ 自定义输入"] + EXAMPLES
selected = st.pills("选择示例问题", examples, default="✍️ 自定义输入")
query = st.text_input(
    "政策问题",
    value="" if selected == "✍️ 自定义输入" else selected,
    placeholder="例如：开办餐饮店需要哪些证照",
)

if st.button("📚 检索政策", type="primary", use_container_width=True, disabled=not _HAS_LOCAL_MODULES):
    if not query.strip():
        st.warning("请输入问题")
    elif not _HAS_LOCAL_MODULES:
        st.warning("模块未安装，无法执行政策检索")
    else:
        with st.spinner("🔄 RAG 检索中（向量检索 → 重排 → 生成）..."):
            agent = PolicyAgent()
            result = run_async(agent.search(query))

        ui.section_header("📄", "回答")
        with st.container(border=True):
            st.markdown(result.answer or "（未生成回答）")

        m1, m2 = st.columns(2)
        with m1:
            ui.metric_card("置信度", f"{result.confidence:.1%}", accent="green")
        with m2:
            ui.metric_card("证据条数", len(result.evidence), accent="blue")

        if result.evidence:
            ui.section_header("📎", "引用证据")
            for ev in result.evidence:
                # PolicyEvidence: source / content / relevance_score（兼容字段名）
                source = getattr(ev, "source", "") or (ev.get("source") if isinstance(ev, dict) else "")
                content = getattr(ev, "content", "") or (ev.get("content") if isinstance(ev, dict) else "")
                score = getattr(ev, "relevance_score", 0) or (ev.get("relevance_score", 0) if isinstance(ev, dict) else 0)
                ui.evidence_card(source, score, content[:200])
        else:
            st.info("本次未返回结构化证据（可能是 LLM 直接生成或模板回答）")
