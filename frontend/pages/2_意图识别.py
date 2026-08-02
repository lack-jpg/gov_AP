"""
frontend.pages.2_意图识别 - 意图分类演示

三级分类链：BERT 模型 → 关键词匹配 → LLM 兜底
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import setup_paths, run_async  # noqa: E402

setup_paths()

from agents.intent.classifier import IntentClassifier  # noqa: E402

st.set_page_config(page_title="意图识别", page_icon="🎯", layout="wide")
st.title("🎯 意图识别")
st.caption("三级分类链：**BERT 模型 → 关键词匹配 → LLM 兜底**")

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

EXAMPLES = [
    "我想开一家餐馆需要什么手续",
    "查询公积金余额",
    "办理房产过户",
    "注册一家科技公司",
    "社保卡怎么办理",
    "发票怎么开具",
    "今天天气怎么样",
]

selected = st.selectbox("选择示例", ["✍️ 自定义输入"] + EXAMPLES)
text = st.text_input(
    "输入文本",
    value="" if selected == "✍️ 自定义输入" else selected,
    placeholder="例如：我想开一家川菜馆",
)

if st.button("🎯 识别意图", type="primary", use_container_width=True):
    if not text.strip():
        st.warning("请输入文本")
    else:
        with st.spinner("识别中..."):
            classifier = IntentClassifier(auto_load=False)
            result = run_async(classifier.classify(text))

        st.divider()
        st.markdown("### 识别结果")

        c1, c2, c3 = st.columns(3)
        c1.metric("🏷️ 意图标签", result.label)
        c2.metric("📛 中文名", LABELS.get(result.label, result.label_name or "-"))
        c3.metric("🔍 识别来源", result.source)

        st.markdown("### 置信度")
        st.progress(min(result.confidence, 1.0))
        st.caption(f"**{result.confidence:.1%}**（≥70% 直接采用，低于则触发 LLM 兜底）")

        if result.label == "policy_query" and result.confidence < 0.6:
            st.info("💡 未匹配到明确业务意图，归为『政策咨询』。可尝试更具体的描述。")

        with st.expander("查看完整结果 (JSON)"):
            st.json(result.model_dump())
