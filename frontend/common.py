"""
frontend.common - Streamlit 前端公共工具：路径设置 + 异步执行

作者: le
日期: 2026/8/2
版本: 0.1
"""
from __future__ import annotations

import asyncio
import os
import sys


def setup_paths() -> None:
    """
    将 frontend/ 和项目根目录加入 sys.path。

    使 Streamlit 页面既能 import 前端 helper（api_client/common），
    也能直接 import 项目模块（agents.* / rag.* / governance.* / tools.*）。
    """
    frontend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(frontend_dir)

    for p in (frontend_dir, project_root):
        if p not in sys.path:
            sys.path.insert(0, p)


def run_async(coro):
    """
    在 Streamlit 同步脚本上下文中运行 async 函数。

    Streamlit 脚本运行在独立线程，通常没有运行中的事件循环；
    若检测到已存在的 loop（如调试器），则创建新 loop 执行。

    Args:
        coro: 协程对象

    Returns:
        协程的返回值
    """
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # 已有运行中的 loop → 新建独立 loop
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
