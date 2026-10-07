"""
tests.test_middleware_safety - 安全中间件不得静默失效

Author: le
Date: 2026/9/29
Version: 0.1
Task: Regression guard for P0 — Auth/RBAC/RateLimit/RequestSizeLimit 加载失败必须可见

背景：
    create_app() 原先对每个中间件单独 try/except/pass，任一导入失败都会让
    鉴权体系静默消失、服务照常启动且无日志。本组测试锁定修复后的行为：
    关键中间件失败 → ERROR 日志 + 严格模式拒启动；状态可被 /health 观测。
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from backend.main import _MIDDLEWARE_SPEC, _register_middlewares


# ============================================================
# 测试替身
# ============================================================


class _FakeApp:
    """最小 FastAPI 替身：仅记录 add_middleware 的调用顺序。"""

    def __init__(self):
        self.registered: list[str] = []

    def add_middleware(self, middleware_cls, **kwargs):
        self.registered.append(middleware_cls.__name__)


class _FakeLogger:
    """收集日志调用的替身，用于断言"失败是否被记录"。"""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg, *args):
        self.errors.append(msg)

    def warning(self, msg, *args):
        self.warnings.append(msg)

    def info(self, msg, *args):
        pass


def _settings(strict: bool) -> SimpleNamespace:
    """构造最小 settings 替身（只需 security_middleware_strict）。"""
    return SimpleNamespace(security_middleware_strict=strict)


def _break_import(monkeypatch, broken_module: str) -> None:
    """让指定模块导入失败，其余模块仍走真实 import。"""
    real_import = importlib.import_module

    def fake_import(name, package=None):
        if name == broken_module:
            raise ImportError(f"模拟 {broken_module} 导入失败")
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)


# ============================================================
# 安全中间件失败语义
# ============================================================


@pytest.mark.parametrize(
    "module_name,middleware_key",
    [
        ("backend.middleware.auth", "auth"),
        ("backend.middleware.rbac", "rbac"),
        ("backend.middleware.rate_limit", "rate_limit"),
        ("backend.middleware.request_size", "request_size"),
    ],
)
def test_security_middleware_failure_rejects_startup(monkeypatch, module_name, middleware_key):
    """严格模式下，任一安全中间件加载失败必须拒绝启动（防止无鉴权裸奔）。"""
    monkeypatch.setattr("backend.main.get_settings", lambda: _settings(True))
    _break_import(monkeypatch, module_name)

    app, logger = _FakeApp(), _FakeLogger()
    with pytest.raises(RuntimeError) as exc:
        _register_middlewares(app, logger)

    assert middleware_key in str(exc.value)
    assert logger.errors, "安全中间件失败必须留下 ERROR 日志，不得静默"


@pytest.mark.parametrize(
    "module_name,middleware_key",
    [
        ("backend.middleware.auth", "auth"),
        ("backend.middleware.rbac", "rbac"),
    ],
)
def test_security_middleware_failure_recorded_when_not_strict(monkeypatch, module_name, middleware_key):
    """非严格模式（本地调试）下不阻断启动，但状态须标记 failed 并记录 ERROR。"""
    monkeypatch.setattr("backend.main.get_settings", lambda: _settings(False))
    _break_import(monkeypatch, module_name)

    app, logger = _FakeApp(), _FakeLogger()
    status = _register_middlewares(app, logger)

    assert status[middleware_key] == "failed"
    assert logger.errors, "即使不拒启动，也必须留下 ERROR 日志"


def test_tracing_failure_does_not_block_startup(monkeypatch):
    """可观测性中间件非安全关键：失败只告警，不阻断启动。"""
    monkeypatch.setattr("backend.main.get_settings", lambda: _settings(True))
    _break_import(monkeypatch, "backend.middleware.tracing")

    app, logger = _FakeApp(), _FakeLogger()
    status = _register_middlewares(app, logger)

    assert status["tracing"] == "failed"
    assert logger.warnings, "非关键中间件失败应留 WARNING"
    assert not logger.errors, "非关键中间件失败不应升级为 ERROR"


def test_all_middlewares_loaded_in_declared_order(monkeypatch):
    """
    注册顺序即执行链（后注册者位于更外层），重构不得打乱。

    当前顺序的实际执行链为：
        request_size → request_logging → auth → rate_limit → rbac → tracing
    """
    monkeypatch.setattr("backend.main.get_settings", lambda: _settings(True))

    app = _FakeApp()
    status = _register_middlewares(app, _FakeLogger())

    expected_order = [class_name for _, _, class_name, _ in _MIDDLEWARE_SPEC]
    assert app.registered == expected_order
    assert set(status.values()) == {"loaded"}


def test_security_middlewares_are_marked_critical():
    """防止后续新增中间件时漏标 critical：安全相关项必须已声明。"""
    critical = {name for name, _, _, is_critical in _MIDDLEWARE_SPEC if is_critical}
    assert {"auth", "rbac", "rate_limit", "request_size"} <= critical


# ============================================================
# 资源释放
# ============================================================


async def test_close_dependencies_releases_clients_and_is_idempotent(monkeypatch):
    """
    close_dependencies 必须释放 MCP / A2A 客户端，且可重复调用。

    背景：此前 A2AConnector.close 只有示例代码调用过，MCPClient 甚至没有
    close 方法，导致 httpx 连接池从未释放。
    """
    import backend.api.dependencies as deps

    class _FakeClient:
        def __init__(self):
            self.closed = 0

        async def close(self):
            self.closed += 1

    mcp_client, a2a_connector = _FakeClient(), _FakeClient()
    monkeypatch.setattr(deps, "_mcp_client", mcp_client)
    monkeypatch.setattr(deps, "_a2a_connector", a2a_connector)
    monkeypatch.setattr(deps, "_agent_graph", object())

    await deps.close_dependencies()

    assert mcp_client.closed == 1, "MCP Client 必须被关闭一次"
    assert a2a_connector.closed == 1, "A2A Connector 必须被关闭一次"
    assert deps._mcp_client is None and deps._a2a_connector is None
    assert deps._agent_graph is None, "图实例持有客户端引用，应一并释放"

    # 幂等：重复调用不应报错，也不应重复关闭
    await deps.close_dependencies()
    assert mcp_client.closed == 1


async def test_close_dependencies_tolerates_client_errors(monkeypatch):
    """关闭过程中客户端抛错时，仍需继续清理其余资源（不中断 shutdown）。"""
    import backend.api.dependencies as deps

    class _BrokenClient:
        async def close(self):
            raise RuntimeError("模拟关闭失败")

    class _OkClient:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    ok_client = _OkClient()
    monkeypatch.setattr(deps, "_mcp_client", _BrokenClient())
    monkeypatch.setattr(deps, "_a2a_connector", ok_client)

    await deps.close_dependencies()  # 不应抛出

    assert ok_client.closed, "前一个客户端关闭失败不应阻断后续清理"
    assert deps._mcp_client is None and deps._a2a_connector is None
