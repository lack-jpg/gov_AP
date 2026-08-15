"""
frontend.app - Streamlit 导航入口

启动方式:
    streamlit run frontend/app.py

登录流程:
    未登录 → 登录页（用户名密码 → POST /api/auth/login 换取 JWT）
    已登录 → 导航页面（首页/智能对话/...），token 注入 api_client 供各页面调用
"""
from __future__ import annotations

import os
import sys

import streamlit as st

# 将 frontend/ 与项目根目录加入 sys.path：
# 项目根必须在前，`from frontend import ui` 才能把 frontend 当作包解析
# （仅加 frontend/ 会导致 streamlit 首次运行时 ModuleNotFoundError）
_frontend_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_frontend_dir)
for _p in (_frontend_dir, _project_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

st.set_page_config(
    page_title="政务多智能体协同平台",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 全局主题 CSS（浅色专业政务风，见 frontend/ui.py）
from frontend import ui  # noqa: E402

ui.inject_theme_css()


def _login_page() -> None:
    """登录页：用户名密码登录，换取 JWT。"""
    st.title("🏛️ 政务多智能体协同平台")
    st.caption("请登录后使用（默认账号见 README 或由管理员提供）")

    with st.form("login_form"):
        username = st.text_input("用户名", placeholder="admin")
        password = st.text_input("密码", type="password", placeholder="请输入密码")
        submitted = st.form_submit_button("登 录", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("请输入用户名和密码")
            return

        from frontend import api_client

        code, data = api_client.login(username.strip(), password)
        if code == 200:
            st.session_state["logged_in"] = True
            st.session_state["username"] = data.get("user_id", username)
            st.session_state["role"] = data.get("role", "")
            st.session_state["token"] = data.get("access_token", "")
            st.rerun()
        else:
            st.error(f"登录失败：{data.get('error', '用户名或密码错误')}")


def _main_app() -> None:
    """登录后的主应用：导航页面 + 侧栏用户信息/登出。"""
    from frontend import api_client

    # 确保 token 注入（Streamlit rerun 时从 session_state 恢复）
    token = st.session_state.get("token", "")
    if token:
        api_client.set_token(token)

    with st.sidebar:
        st.markdown(f"**👤 {st.session_state.get('username', '')}**")
        st.caption(f"角色：{st.session_state.get('role', '')}")
        if st.button("退出登录", use_container_width=True):
            api_client.logout()
            for _k in ("logged_in", "username", "role", "token"):
                st.session_state.pop(_k, None)
            st.rerun()

    pages = [
        st.Page("pages/home_page.py", title="首页", icon="🏠", default=True),
        st.Page("pages/chat_page.py", title="智能对话", icon="💬"),
        st.Page("pages/intent_page.py", title="意图识别", icon="🎯"),
        st.Page("pages/policy_page.py", title="政策检索", icon="📚"),
        st.Page("pages/material_page.py", title="材料审核", icon="📋"),
        st.Page("pages/a2a_page.py", title="跨域协同", icon="🤝"),
        st.Page("pages/governance_page.py", title="安全治理", icon="🛡️"),
        st.Page("pages/dashboard_page.py", title="运维看板", icon="📊"),
    ]
    pg = st.navigation(pages)
    pg.run()


if st.session_state.get("logged_in"):
    _main_app()
else:
    _login_page()
