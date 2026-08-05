"""
frontend.pages.a2a_page - A2A 跨域 Agent 协同演示

通过 A2A 协议调用外部系统（不动产 / 公积金）Mock Agent
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from frontend.common import setup_paths, run_async  # noqa: E402

setup_paths()

try:
    from tools.a2a.mock_agents.housing_agent import HousingAgent  # noqa: E402
    from tools.a2a.mock_agents.fund_agent import FundAgent  # noqa: E402
    from tools.a2a.protocol import A2ATaskRequest  # noqa: E402
    _HAS_LOCAL_MODULES = True
except ImportError:
    HousingAgent = None  # type: ignore[assignment]
    FundAgent = None  # type: ignore[assignment]
    A2ATaskRequest = None  # type: ignore[assignment]
    _HAS_LOCAL_MODULES = False


st.title("🤝 跨域协同（A2A）")
st.caption("通过 **A2A 协议**调用外部系统 Agent：本地政务 Agent → 不动产系统 / 公积金系统")

if not _HAS_LOCAL_MODULES:
    st.warning(
        "⚠️ 此功能依赖项目本地模块（`tools/a2a/`），当前 Docker 容器中未包含。\n\n"
        "请本地运行以获得完整体验：\n"
        "```bash\n"
        "pip install -r requirements/requirements.txt\n"
        "streamlit run frontend/app.py\n"
        "```\n\n"
        "💡 提示：Docker 中 A2A 协同由后端 API（`POST /api/a2a/callback`）处理，"
        "可通过 **智能对话** 页触发跨域查询。"
    )

agent_type = st.radio(
    "选择外部 Agent",
    ["🏠 不动产系统 (housing_agent)", "🏦 公积金系统 (fund_agent)"],
    horizontal=True,
)

st.divider()

if "不动产" in agent_type:
    st.subheader("🏠 不动产查询")
    owner = st.text_input("户主姓名", "张三")
    detail = st.checkbox("同时返回关联公积金余额", value=True)

    if st.button("🔍 查询不动产", type="primary", use_container_width=True, disabled=not _HAS_LOCAL_MODULES):
        if not _HAS_LOCAL_MODULES:
            st.warning("模块未安装，无法执行 A2A 查询")
        else:
            with st.spinner("🔄 调用外部不动产 Agent..."):
                agent = HousingAgent()
                req = A2ATaskRequest(
                    task_id="demo_housing",
                    skill="query_property",
                    input={"owner_name": owner},
                )
                resp = run_async(agent.process_task(req))

            st.divider()
            st.markdown(f"### 查询结果  ·  `{resp.status.value}`")
            artifact = resp.artifact or {}
            properties = artifact.get("properties", [])
            st.caption(f"共找到 **{artifact.get('total_count', 0)}** 处不动产")

            if properties:
                for p in properties:
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 2])
                        c1.markdown(f"**{p.get('address')}**")
                        c1.caption(f"产权证号: {p.get('property_right_no', '-')}")
                        c2.markdown(f"- 类型: {p.get('type')}")
                        c2.markdown(f"- 面积: {p.get('area_sqm')}㎡")
                        c2.markdown(f"- 抵押: {p.get('mortgage_status', '-')}")
            else:
                st.warning("未找到匹配的不动产记录")

            if detail and artifact.get("housing_fund"):
                st.info(f"🏦 关联公积金余额: **{artifact['housing_fund'][0].get('balance')}** 元")

else:
    st.subheader("🏦 公积金查询")
    user_id = st.text_input("用户 ID", "001")
    user_name = st.text_input("用户姓名（可选）", "")
    show_detail = st.checkbox("显示提取记录详情", value=False)

    if st.button("🔍 查询公积金", type="primary", use_container_width=True, disabled=not _HAS_LOCAL_MODULES):
        if not _HAS_LOCAL_MODULES:
            st.warning("模块未安装，无法执行 A2A 查询")
        else:
            with st.spinner("🔄 调用外部公积金 Agent..."):
                agent = FundAgent()
                skill = "query_fund_detail" if show_detail else "query_fund"
                req = A2ATaskRequest(
                    task_id="demo_fund",
                    skill=skill,
                    input={"user_id": user_id, "user_name": user_name},
                )
                resp = run_async(agent.process_task(req))

            st.divider()
            st.markdown(f"### 查询结果  ·  `{resp.status.value}`")
            artifact = resp.artifact or {}
            accounts = artifact.get("fund_accounts") or artifact.get("fund_details") or []
            st.caption(f"共找到 **{artifact.get('total_count', 0)}** 个公积金账户")

            for acc in accounts:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("账户", acc.get("account_no", "-"))
                    c2.metric("余额", f"{acc.get('balance', 0):,.2f} 元")
                    c3.metric("状态", acc.get("account_status", "-"))
                    st.caption(f"单位: {acc.get('unit_name', '-')} · 缴存比例: {acc.get('unit_ratio', '-')} / {acc.get('personal_ratio', '-')}")

                if show_detail and acc.get("withdrawal_records"):
                    st.markdown("**提取记录：**")
                    for rec in acc["withdrawal_records"]:
                        st.markdown(f"- {rec.get('date')}  {rec.get('reason')}  **{rec.get('amount'):,.0f}** 元 ({rec.get('status')})")

            if artifact.get("max_loan_amount"):
                st.success(f"💰 最高可贷额度: **{artifact['max_loan_amount']:,.0f}** 元（最长 {artifact.get('max_loan_years', '-')} 年）")

st.divider()
st.caption("💡 说明：以上为 Mock 外部 Agent（`tools/a2a/mock_agents`），生产环境通过 A2A 协议对接真实系统。"
           "本页直接调用本地模块；完整 HTTP 链路见 API 后端的 A2A Connector。")
