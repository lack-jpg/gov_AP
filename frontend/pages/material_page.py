"""
frontend.pages.material_page - 材料完整性校验演示

按业务类型校验提交材料，支持别名匹配、模糊匹配、温馨提示
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from frontend.common import setup_paths, run_async  # noqa: E402
from frontend import ui  # noqa: E402

setup_paths()

# MaterialValidator — 纯规则校验，无外部依赖
try:
    from agents.material.validator import MaterialValidator  # noqa: E402
    _HAS_VALIDATOR = True
except ImportError:
    MaterialValidator = None  # type: ignore[assignment]
    _HAS_VALIDATOR = False

# MaterialAgent — 依赖 langchain，Docker 中不可用
try:
    from agents.material.agent import MaterialAgent  # noqa: E402
    _HAS_AGENT = True
except ImportError:
    MaterialAgent = None  # type: ignore[assignment]
    _HAS_AGENT = False

_HAS_LOCAL_MODULES = _HAS_VALIDATOR

# ============================================================
# 页头
# ============================================================
ui.page_header("📋", "材料审核", "按业务类型校验材料完整性 · 别名匹配 · 温馨提示")

if not _HAS_LOCAL_MODULES:
    st.warning(
        "⚠️ 此功能依赖项目本地模块（`agents/material/`），当前 Docker 容器中未包含。\n\n"
        "请本地运行以获得完整体验：\n"
        "```bash\n"
        "pip install -r requirements/requirements.txt\n"
        "streamlit run frontend/app.py\n"
        "```"
    )

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

# 必需材料清单（MaterialValidator 不可用时用硬编码 fallback）
if _HAS_VALIDATOR:
    _REQUIRED = MaterialValidator.REQUIRED_MATERIALS
else:
    _REQUIRED = {
        "restaurant_license": ["身份证", "经营场所证明（租赁合同或房产证）", "营业执照申请表", "食品经营许可申请书", "从业人员健康证", "食品安全管理制度", "消防安全检查申请表"],
        "business_license": ["身份证", "经营场所证明（租赁合同或房产证）", "营业执照申请表", "名称预先核准通知书"],
        "business_register": ["法人身份证", "经营场所证明（租赁合同或房产证）", "公司章程", "股东会决议", "公司登记申请书"],
        "property_service": ["身份证", "不动产权证书（或购房合同）", "不动产登记申请书", "完税证明"],
        "fund_query": ["身份证", "公积金查询申请表"],
    }

c1, c2 = st.columns([1, 2])
with c1:
    bt = st.selectbox("业务类型", list(BUSINESS_TYPES.keys()), format_func=lambda k: BUSINESS_TYPES[k])
with c2:
    st.markdown("**必需材料清单：**")
    required = _REQUIRED.get(bt, [])
    st.markdown(" ".join(ui.pill(r, "gray") for r in required), unsafe_allow_html=True)

materials_str = st.text_area(
    "已提交材料（用逗号或顿号分隔）",
    value=EXAMPLES.get(bt, ""),
    height=80,
    help="支持别名，如『身份证明』自动匹配『身份证』",
)

if st.button("📋 审核材料", type="primary", use_container_width=True, disabled=not _HAS_LOCAL_MODULES):
    if not _HAS_LOCAL_MODULES:
        st.warning("模块未安装，无法执行材料审核")
    else:
        materials = [m.strip() for m in materials_str.replace("，", ",").replace("、", ",").split(",") if m.strip()]
        with st.spinner("校验中..."):
            if _HAS_AGENT:
                agent = MaterialAgent()
                result = run_async(agent.review(business_type=bt, submitted_materials=materials))
            else:
                validator = MaterialValidator()
                result = run_async(validator.validate(business_type=bt, materials=materials))

        ui.section_header("📋", "审核结果")

        if result.get("passed") if isinstance(result, dict) else result.passed:
            ui.status_card(True, "材料齐全，可以继续办理！")
        else:
            missing_count = len(result.get("missing", [])) if isinstance(result, dict) else len(result.missing)
            ui.status_card(False, "材料不完整", f"缺少 {missing_count} 项")

        missing = result.get("missing", []) if isinstance(result, dict) else result.missing
        warnings_list = result.get("warnings", []) if isinstance(result, dict) else result.warnings

        col_missing, col_submitted = st.columns(2)
        with col_missing:
            if missing:
                with st.container(border=True):
                    st.markdown("**❌ 缺失材料**")
                    for m in missing:
                        st.markdown(f"- {m}")
        with col_submitted:
            if not missing:
                with st.container(border=True):
                    st.markdown("**✅ 已提交材料**")
                    for m in materials:
                        st.markdown(f"- {m}")

        if warnings_list:
            with st.container(border=True):
                st.markdown("**⚠️ 温馨提示**")
                for w in warnings_list:
                    st.markdown(f"- {w}")

        st.caption(f"已提交 {len(materials)} 项 · 缺失 {len(missing)} 项 · 提示 {len(warnings_list)} 条")
