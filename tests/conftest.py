"""
tests.conftest - pytest fixtures and shared setup
"""
from __future__ import annotations

import os
import sys

import pytest

# 确保项目根目录在 sys.path 中（当 pytest 从根目录运行时已包含，但显式添加更稳妥）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── 测试环境配置基线（必须在任何 backend.config / gateway 导入之前设置）──
# CI 无 .env（被 .gitignore 排除），而 tools/mcp/gateway 模块导入时会执行
# validate_security_config()：非 debug + 默认 'changeme' 密钥会抛 RuntimeError。
# 此处统一注入合法测试配置，保证测试套件不依赖本机 .env / 外部环境变量即可复现。
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["DEBUG"] = "true"


@pytest.fixture
def initial_state():
    """创建初始 AgentState"""
    from orchestration.langgraph.state import create_initial_state

    return create_initial_state(user_query="我想开一家餐馆需要什么手续")


@pytest.fixture
def sample_query() -> str:
    """样例用户查询"""
    return "我想在成都开一家川菜馆，需要什么手续和材料"


@pytest.fixture
def stub_graph():
    """无 LLM 的 stub 模式图"""
    from orchestration.langgraph.graph import create_default_graph

    return create_default_graph()
