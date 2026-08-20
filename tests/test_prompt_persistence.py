"""
test_prompt_persistence - P2-4 Prompt Registry 持久化闭环测试

验证：
1. PromptTemplate(content=...) 渲染优先返回 content 且变量可替换（含单大括号 {var}）；
2. _preload_defaults 含 SUPERVISOR_SYNTHESIS_PROMPT，渲染时变量正确替换；
3. to_db_dict 写入渲染文本 content；
4. flush_to_db 幂等 upsert：重复调用不产生重复行、正确落 is_active；
5. load_from_db 重建模板带 content，round-trip 后渲染非空。
"""
from __future__ import annotations

import pytest
import sqlalchemy

from prompts.registry import PromptTemplate, get_registry, reset_registry


class TestContentRendering:
    def test_content_preferred_over_sections(self):
        pt = PromptTemplate(
            name="T", agent_name="test",
            content="你好 {{ name }}",
            role="不该被渲染",
        )
        assert pt.render(name="张三") == "你好 张三"

    def test_single_brace_substitution(self):
        pt = PromptTemplate(
            name="T", agent_name="test",
            content="用户: {user_query}",
            variables=["user_query"],
        )
        assert pt.render(user_query="查公积金") == "用户: 查公积金"

    def test_single_brace_does_not_break_json(self):
        # 单大括号归一化只作用于声明的变量，JSON 键（带引号）不受影响
        pt = PromptTemplate(
            name="T", agent_name="test",
            content='{"answer": "{{ ans }}", "list": [1, 2]}',
            variables=["ans"],
        )
        assert pt.render(ans="你好") == '{"answer": "你好", "list": [1, 2]}'

    def test_supervisor_synthesis_preloaded_and_rendered(self):
        reset_registry()
        t = get_registry().get("SUPERVISOR_SYNTHESIS_PROMPT")
        assert t is not None
        out = t.render(
            user_query="查政策", intent_result="x", policy_result="y",
            material_result="z", workflow_result="w",
        )
        assert "查政策" in out
        assert "{user_query}" not in out
        assert "{policy_result}" not in out


class TestDbDict:
    def test_to_db_dict_contains_rendered_content(self):
        pt = PromptTemplate(
            name="T", agent_name="test", content="你好 {{ name }}",
        )
        d = pt.to_db_dict()
        assert d["content"] == "你好 {{ name }}"
        assert d["name"] == "T"
        assert d["is_active"] is True

    def test_to_db_dict_without_content_renders_sections(self):
        pt = PromptTemplate(
            name="T", agent_name="test", role="你是{{ name }}",
        )
        d = pt.to_db_dict()
        assert "你是{{ name }}" in d["content"]


# ============================================================
# 假 DB 会话：模拟 database.connection.get_session_factory
# ============================================================


def _where_pairs(stmt) -> list[tuple[str, object]]:
    """从 SQLAlchemy select 语句提取 (列名, 值) 条件对。"""
    where = getattr(stmt, "whereclause", None)
    if where is None:
        return []
    if isinstance(where, sqlalchemy.sql.elements.BooleanClauseList):
        exprs = list(where.get_children())
    else:
        exprs = [where]
    pairs: list[tuple[str, object]] = []
    for e in exprs:
        if isinstance(e, sqlalchemy.sql.elements.BinaryExpression):
            col = getattr(getattr(e, "left", None), "key", None)
            right = getattr(e, "right", None)
            val = getattr(right, "value", None)
            if val is None and hasattr(right, "effective_value"):
                val = right.effective_value
            pairs.append((col, val))
    return pairs


def _make_session_factory(sink: dict):
    """构造可追踪 add/execute/commit 的假 session 工厂。"""

    class _ScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return list(self._rows)

        def first(self):
            return self._rows[0] if self._rows else None

    class _ExecResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _ScalarResult(self._rows)

    class _Session:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def execute(self, stmt):
            rows = sink["store"]
            for col, val in _where_pairs(stmt):
                if col and val is not None:
                    rows = [r for r in rows if getattr(r, col) == val]
            return _ExecResult(rows)

        async def commit(self):
            sink["store"].extend(self.added)
            self.added = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Factory:
        def __call__(self):
            return _Session()

    return _Factory()


class TestFlushIdempotent:
    @pytest.mark.asyncio
    async def test_repeat_flush_no_duplicate_rows(self, monkeypatch):
        reset_registry()
        registry = get_registry()
        sink: dict = {"store": []}
        monkeypatch.setattr(
            "database.connection.get_session_factory",
            lambda: _make_session_factory(sink),
        )

        n1 = await registry.flush_to_db()
        n2 = await registry.flush_to_db()

        assert n1 > 0
        assert n2 > 0
        # 幂等：重复 flush 不产生重复行
        assert len(sink["store"]) == n1

    @pytest.mark.asyncio
    async def test_flush_persists_is_active(self, monkeypatch):
        reset_registry()
        registry = get_registry()
        sink: dict = {"store": []}
        monkeypatch.setattr(
            "database.connection.get_session_factory",
            lambda: _make_session_factory(sink),
        )

        # 注册 v2 并激活，v1 自动停用
        registry.register(PromptTemplate(
            name="SUPERVISOR_SYSTEM_PROMPT", agent_name="supervisor", version="v2",
            content="v2 内容",
        ))
        registry.activate_version("SUPERVISOR_SYSTEM_PROMPT", "v2")
        await registry.flush_to_db("SUPERVISOR_SYSTEM_PROMPT")

        rows = [r for r in sink["store"] if r.name == "SUPERVISOR_SYSTEM_PROMPT"]
        assert len(rows) == 2
        active = [r for r in rows if r.is_active]
        assert len(active) == 1
        assert active[0].version == "v2"


class TestLoadRoundTrip:
    @pytest.mark.asyncio
    async def test_load_from_db_restores_content(self, monkeypatch):
        reset_registry()
        registry = get_registry()
        sink: dict = {"store": []}
        monkeypatch.setattr(
            "database.connection.get_session_factory",
            lambda: _make_session_factory(sink),
        )

        # 先落库
        await registry.flush_to_db()
        db_rows = list(sink["store"])

        # 全新 registry 从 DB 加载
        reset_registry()
        fresh = get_registry()
        loaded = await fresh.load_from_db()

        assert loaded == len(db_rows)
        # round-trip 后渲染非空（content 被正确重建）
        t = fresh.get("SUPERVISOR_SYSTEM_PROMPT")
        assert t is not None
        rendered = t.render(user_query="开餐饮店", intent="business_license")
        assert "开餐饮店" in rendered

    @pytest.mark.asyncio
    async def test_load_empty_db_falls_back_to_defaults(self, monkeypatch):
        reset_registry()
        registry = get_registry()
        sink: dict = {"store": []}
        monkeypatch.setattr(
            "database.connection.get_session_factory",
            lambda: _make_session_factory(sink),
        )

        loaded = await registry.load_from_db()
        assert loaded == 0
        # 空表时内置默认模板仍可用
        assert registry.get("INTENT_CLASSIFIER_PROMPT") is not None
