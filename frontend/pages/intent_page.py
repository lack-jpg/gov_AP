"""
frontend.pages.intent_page - 意图分类演示

三级分类链：BERT 模型 → 关键词匹配 → LLM 兜底
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
    from agents.intent.classifier import IntentClassifier  # noqa: E402
    _HAS_LOCAL_MODULES = True
except ImportError:
    IntentClassifier = None  # type: ignore[assignment]
    _HAS_LOCAL_MODULES = False

# ============================================================
# 页头
# ============================================================
ui.page_header("🎯", "意图识别", "三级分类链：**BERT 模型 → 关键词匹配 → LLM 兜底**")

if not _HAS_LOCAL_MODULES:
    st.warning(
        "⚠️ 此功能依赖项目本地模块（`agents/`），当前 Docker 容器中未包含。\n\n"
        "请本地运行以获得完整体验：\n"
        "```bash\n"
        "pip install -r requirements/requirements.txt\n"
        "streamlit run frontend/app.py\n"
        "```"
    )

# 支持的业务意图
LABELS = {
    "restaurant_license": "餐饮许可（开餐馆）",
    "business_license": "营业执照（个体户）",
    "business_register": "企业注册",
    "fund_query": "公积金查询",
    "property_service": "不动产服务",
    "medical_insurance": "医保服务",
    "social_security": "社保服务",
    "tax_service": "税务服务",
    "policy_query": "政策咨询",
    "other": "其他事项",
}

SOURCE_NAMES = {
    "bert": "微调 BERT",
    "keyword": "关键词匹配",
    "llm": "LLM 兜底",
}

EXAMPLES = [
    "我想开一家餐馆需要什么手续",
    "查询公积金余额",
    "办理房产过户",
    "注册一家科技公司",
    "社保卡怎么办理",
    "发票怎么开具",
    "今天天气怎么样",
]

examples = ["✍️ 自定义输入"] + EXAMPLES
selected = st.pills("选择示例", examples, default="✍️ 自定义输入")
text = st.text_input(
    "输入文本",
    value="" if selected == "✍️ 自定义输入" else selected,
    placeholder="例如：我想开一家川菜馆",
)

if st.button("🎯 识别意图", type="primary", use_container_width=True, disabled=not _HAS_LOCAL_MODULES):
    if not text.strip():
        st.warning("请输入文本")
    elif not _HAS_LOCAL_MODULES:
        st.warning("模块未安装，无法执行意图识别")
    else:
        with st.spinner("识别中..."):
            classifier = IntentClassifier()  # auto_load=True，使用本地微调 BERT 模型
            result = run_async(classifier.classify(text))

        ui.section_header("📊", "识别结果")

        c1, c2, c3 = st.columns(3)
        with c1:
            ui.metric_card("🏷️ 意图", LABELS.get(result.label, result.label_name or result.label), accent="blue")
        with c2:
            ui.metric_card("📛 英文标签", result.label, accent="gray")
        with c3:
            ui.metric_card("🔍 识别来源", SOURCE_NAMES.get(result.source, result.source), accent="green")

        with st.container(border=True):
            st.markdown("**置信度**")
            st.progress(min(result.confidence, 1.0))
            st.caption(f"**{result.confidence:.1%}**（≥70% 直接采用，低于则触发 LLM 兜底）")

        if result.label == "policy_query" and result.confidence < 0.6:
            st.info("💡 未匹配到明确业务意图，归为『政策咨询』。可尝试更具体的描述。")

        with st.expander("查看完整结果 (JSON)"):
            st.json(result.model_dump())
