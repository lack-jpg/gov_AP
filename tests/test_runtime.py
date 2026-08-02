"""
test_runtime - AgentRuntime safeguards tests (step limit, loop detection)
"""
from __future__ import annotations

import pytest

from orchestration.langgraph.runtime import (
    AgentRuntime,
    LoopDetector,
    RuntimeConfig,
    RuntimeExceededError,
    create_runtime_from_settings,
)


class TestLoopDetector:
    def test_no_loop_on_mixed(self):
        ld = LoopDetector(window_size=6, threshold=3)
        ld.feed("search_policy")
        ld.feed("check_material")
        ld.feed("search_policy")
        assert ld._check_loop() is False

    def test_loop_after_3_same(self):
        ld = LoopDetector(window_size=6, threshold=3)
        assert ld.feed("search_policy") is False
        assert ld.feed("search_policy") is False
        assert ld.feed("search_policy") is True

    def test_reset(self):
        ld = LoopDetector(window_size=6, threshold=3)
        ld.feed("a")
        ld.reset()
        assert len(ld.recent_tools) == 0


class TestAgentRuntime:
    def test_step_limit(self):
        rt = AgentRuntime(config=RuntimeConfig(max_steps=3))
        from orchestration.langgraph.state import create_initial_state
        state = create_initial_state(user_query="test")

        rt.check_step(state)
        rt.check_step(state)
        rt.check_step(state)
        with pytest.raises(RuntimeExceededError):
            rt.check_step(state)
        assert rt.step_count == 4

    def test_error_accumulation(self):
        rt = AgentRuntime(config=RuntimeConfig(max_steps=100, max_error_count=2))
        from orchestration.langgraph.state import create_initial_state
        state = create_initial_state(user_query="test")

        rt.check_step({**state, "error": "err1"})
        rt.check_step({**state, "error": "err2"})
        with pytest.raises(RuntimeExceededError):
            rt.check_step({**state, "error": "err3"})
        assert rt.error_count == 3


class TestFactory:
    def test_default(self):
        rt = create_runtime_from_settings()
        assert rt.config.max_steps == 10

    def test_custom_settings(self):
        from dataclasses import dataclass

        @dataclass
        class FakeSettings:
            agent_max_steps: int = 5
            agent_loop_window: int = 4
            agent_timeout: int = 15

        rt = create_runtime_from_settings(FakeSettings())
        assert rt.config.max_steps == 5
        assert rt.config.loop_window_size == 4
        assert rt.config.agent_timeout == 15
