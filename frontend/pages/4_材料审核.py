"""
frontend.pages.4_材料审核 - 材料完整性校验演示

按业务类型校验提交材料，支持别名匹配、模糊匹配、温馨提示
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import setup_paths, run_async  # noqa: E402

setup_paths()

from agents.material.agent import MaterialAgent  # noqa: E402
from agents.material.validator import MaterialValidator  # noqa: E402

st.set_page_config(page_title="材料审核", page_icon="📋", layout="wide")
st.title("📋 材料审核")
st.caption("按业务类型校验材料完整性 · 别名匹配 · 温馨提示")

BUSINESS_TYPES = {
    "restaurant_license": "🍜 餐饮许可（开餐馆）",
    "business_license": "🏪 营业执照（个体户）",
    "business_register": "🏢 企业注册",
    "property_service": "🏠 不动产服务",
    "fund_query": "🏦 公积金查询",
}

EXAMPLES = {
    "restaurant_license": "身份证, 经营场所证明, 营业执照申请表, 食品经营许可申请书, 从业人员健康证, 食品安全管理制度, 消防安全检查申请表",
    "business_license": "身份证, 经营场所证明, 营业执照申请表, 名称预先核准通知书",
    "business_register": "法人身份证, 经营场所证明, 公司章程, 股东会决议, 公司登记申请书",
    "property_service": "身份证, 不动产权证书, 不动产登记申请书, 完税证明",
    "fund_query": "身份证, 公积金查询申请表",
}

c1, c2 = st.columns(2)
with c1:
    bt = st.selectbox("业务类型", list(BUSINESS_TYPES.keys()), format_func=lambda k: BUSINESS_TYPES[k])
with c2:
    st.caption("")
    st.caption("**必需材料清单：**")
    st.caption(MaterialValidator.REQUIRED_MATERIALS.get(bt, []))

materials_str = st.text_area(
    "已提交材料（用逗号或顿号分隔）",
    value=EXAMPLES.get(bt, ""),
    height=80,
    help="支持别名，如『身份证明』自动匹配『身份证』",
)

if st.button("📋 审核材料", type="primary", use_container_width=True):
    materials = [m.strip() for m in materials_str.replace("，", ",").replace("、", ",").split(",") if m.strip()]
    with st.spinner("校验中..."):
        agent = MaterialAgent()
        result = run_async(agent.review(business_type=bt, submitted_materials=materials))

    st.divider()
    st.markdown("### 审核结果")

    if result.passed:
        st.success("✅ **材料齐全，可以继续办理！**")
    else:
        st.error(f"❌ **材料不完整**，缺少 {len(result.missing)} 项")

    if result.missing:
        st.subheader("❌ 缺失材料")
        for m in result.missing:
            st.markdown(f"- {m}")
    else:
        st.subheader("✅ 已提交材料")
        for m in materials:
            st.markdown(f"- {m}")

    if result.warnings:
        st.subheader("⚠️ 温馨提示")
        for w in result.warnings:
            st.markdown(f"- {w}")

    st.caption(f"已提交 {len(materials)} 项 · 缺失 {len(result.missing)} 项 · 提示 {len(result.warnings)} 条")
