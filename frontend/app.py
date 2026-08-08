"""
frontend.app - Streamlit 导航入口

启动方式:
    streamlit run frontend/app.py

页面导航由 st.navigation() 显式定义，不依赖数字前缀文件名。
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
