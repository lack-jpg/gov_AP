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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(
    page_title="政务多智能体协同平台",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
