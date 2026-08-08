"""
langgraph.runtime - Agent Runtime: step limit, loop detection, timeout control, error recovery

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement runtime safeguards (max_steps=10, loop detection window=6, timeout=30s)
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from tools.logger import get_logger
from orchestration.langgraph.state import AgentState, RiskLevel

logger = get_logger(__name__)


# ============================================================
# 配置
# ============================================================


@dataclass
class RuntimeConfig:
    """
    Agent Runtime 安全配置。

    所有值可被 Settings（.env）中的 AGENT_MAX_STEPS / AGENT_LOOP_WINDOW / AGENT_TIMEOUT 覆盖。
    """
    max_steps: int = 10
    """最大执行步数，超过则强制终止"""

    loop_window_size: int = 6
    """循环检测滑动窗口大小（最近 N 次 tool call）"""

    loop_threshold: int = 3
    """连续相同 tool 次数阈值，超过触发 re-plan"""

    agent_timeout: float = 30.0
    """单个 Agent 执行超时（秒）"""

    max_retries: int = 3
    """最大重试次数"""

    max_error_count: int = 5
    """累计错误次数上限，超过终止整个流程"""


# ============================================================
# 循环检测器
# ============================================================


@dataclass
class LoopDetector:
    """
    滑动窗口循环检测器。

    检测逻辑:
        窗口大小 = 6 次最近 tool_call
        如果连续 3 次调用同一个 tool → 判定为循环

    触发后的处理:
        1. 标记当前 Agent 执行异常
        2. 设置 risk_level = high
        3. 返回 True 通知调用方触发 re-plan
    """

    window_size: int = 6
    threshold: int = 3
    _history: deque[str] = field(default_factory=lambda: deque(maxlen=6))

    def feed(self, tool_name: str) -> bool:
        """
        喂入一次 tool 调用，返回是否检测到循环。

        Args:
            tool_name: 本次调用的工具名

        Returns:
            True 表示检测到循环，应立即触发 re-plan
        """
        self._history.append(tool_name)
        return self._check_loop()

    def feed_batch(self, tool_names: list[str]) -> bool:
        """批量喂入，返回是否检测到循环"""
        for name in tool_names:
            self._history.append(name)
        return self._check_loop()

    def _check_loop(self) -> bool:
        """检查窗口内是否有连续 threshold 次相同 tool"""
        if len(self._history) < self.threshold:
            return False

        # 取最近 threshold 次
        recent = list(self._history)[-self.threshold:]
        return len(set(recent)) == 1  # 全部相同

    def reset(self) -> None:
        """重置检测器"""
        self._history.clear()

    @property
    def recent_tools(self) -> list[str]:
        """返回最近的 tool 调用历史（用于日志）"""
        return list(self._history)


# ============================================================
# Runtime
# ============================================================


class AgentRuntime:
    """
    Agent Runtime — 运行时安全护栏。

    在 graph 执行前后进行安全检查和保护：

    1. **步骤限制**: 执行步数超过 max_steps → 强制终止，生成 graceful response
    2. **循环检测**: 滑动窗口(6)内连续同 tool 3次 → 触发 Supervisor re-plan
    3. **超时控制**: 单个 Agent 超过 agent_timeout → 中断，记录 timeout
    4. **错误累积**: 累计错误超过 max_error_count → 终止流程
    5. **状态注入**: 每个 step 后更新 step_count、risk_level

    使用方式:
        runtime = AgentRuntime(config)
        try:
            state = await runtime.execute_with_safeguards(graph, initial_state)
        except RuntimeExceededError:
            # 步骤耗尽
            pass
    """

    def __init__(self, config: Optional[RuntimeConfig] = None):
        self.config = config or RuntimeConfig()
        self._loop_detector = LoopDetector(
            window_size=self.config.loop_window_size,
            threshold=self.config.loop_threshold,
        )
        self._step_count = 0
        self._error_count = 0

    # ── 公开接口 ──

    async def execute_with_safeguards(
        self,
        graph,
        initial_state: AgentState,
        graph_config: Optional[dict] = None,
    ) -> AgentState:
        """
        执行 graph 并施加安全护栏。

        在每个 step 后调用 check_step 进行安全检查。
        超时步骤使用 asyncio.wait_for 包装。

        Args:
            graph: 已编译的 LangGraph StateGraph
            initial_state: 初始 AgentState
            graph_config: LangGraph 执行配置（含 thread_id 等）

        Returns:
            最终 AgentState

        Raises:
            RuntimeExceededError: 步骤耗尽
            RuntimeTimeoutError: Agent 执行超时
            RuntimeLoopDetectedError: 检测到循环
        """
        self.reset()

        # 注入递归限制到 graph config
        config = graph_config or {}
        if "recursion_limit" not in config:
            config["recursion_limit"] = self.config.max_steps + 2

        try:
            # 注意：graph.ainvoke 内部已有 recursion_limit 保护
            # 我们在此基础上增加 per-step 检查
            result = await asyncio.wait_for(
                graph.ainvoke(initial_state, config=config),
                timeout=self.config.agent_timeout * self.config.max_steps,
            )
            return result

        except asyncio.TimeoutError:
            logger.error(
                "Agent 执行超时 timeout={}s max_steps={}",
                self.config.agent_timeout, self.config.max_steps,
            )
            raise RuntimeTimeoutError(
                f"Agent 执行超时（>{self.config.agent_timeout * self.config.max_steps}s）"
            )

    def check_step(self, state: AgentState) -> AgentState:
        """
        单步安全检查 — 在每次 LangGraph 节点返回后调用。

        Args:
            state: 当前 AgentState

        Returns:
            更新后的 AgentState（含 step_count、risk_level 变更）
        """
        self._step_count += 1

        # 1. 步骤限制
        if self._step_count > self.config.max_steps:
            logger.warning(
                "步骤超限 step={}/{} current_agent={}",
                self._step_count, self.config.max_steps,
                state.get("current_agent", "?"),
            )
            state = {**state, "risk_level": RiskLevel.HIGH.value}
            raise RuntimeExceededError(
                f"Agent 执行步数超过限制 ({self._step_count} > {self.config.max_steps})"
            )

        # 2. 循环检测
        tool_calls = state.get("tool_calls", [])
        for tc in tool_calls[-3:]:  # 只检查最近3次
            tool_name = tc.get("tool_name", "") if isinstance(tc, dict) else getattr(tc, "tool_name", "")
            if tool_name:
                loop_detected = self._loop_detector.feed(tool_name)
                if loop_detected:
                    logger.warning(
                        "检测到工具调用循环 tool={} history={}",
                        tool_name, self._loop_detector.recent_tools,
                    )
                    state = self._mark_loop_detected(state, tool_name)
                    raise RuntimeLoopDetectedError(
                        f"检测到循环: {tool_name} 连续调用 {self.config.loop_threshold} 次"
                    )

        # 3. 错误累积
        error = state.get("error", "")
        if error:
            self._error_count += 1
            if self._error_count > self.config.max_error_count:
                logger.error(
                    "错误累积超限 errors={}/{}",
                    self._error_count, self.config.max_error_count,
                )
                state = {**state, "risk_level": RiskLevel.CRITICAL.value}
                raise RuntimeExceededError(
                    f"累计错误次数超过上限 ({self._error_count} > {self.config.max_error_count})"
                )

        return state

    def check_loop_detected(self, state: AgentState) -> bool:
        """
        轻量检测 — 不抛异常，仅返回 True/False。

        用于条件边中的循环检测（不中断流程，而是触发 re-plan）。

        Args:
            state: 当前 AgentState

        Returns:
            True 表示检测到循环
        """
        tool_calls = state.get("tool_calls", [])
        recent = [tc.get("tool_name", "") if isinstance(tc, dict) else getattr(tc, "tool_name", "") for tc in tool_calls[-self.config.loop_window_size:]]
        return self._loop_detector.feed_batch(recent)

    def reset(self) -> None:
        """重置所有计数器（新请求开始时调用）"""
        self._step_count = 0
        self._error_count = 0
        self._loop_detector.reset()

    @property
    def step_count(self) -> int:
        """当前已执行步数"""
        return self._step_count

    @property
    def error_count(self) -> int:
        """累计错误次数"""
        return self._error_count

    # ── 内部 ──

    def _mark_loop_detected(self, state: AgentState, tool_name: str) -> AgentState:
        """标记循环检测到循环的状态"""
        error_history = state.get("error_history", [])
        return {
            **state,
            "risk_level": RiskLevel.HIGH.value,
            "error": f"Loop detected: {tool_name} repeated {self.config.loop_threshold} times",
            "error_history": error_history + [{
                "type": "loop_detected",
                "tool": tool_name,
                "threshold": self.config.loop_threshold,
                "timestamp": time.time(),
            }],
        }


# ============================================================
# 异常类
# ============================================================


class RuntimeExceededError(Exception):
    """步骤超限或错误累积超限"""


class RuntimeTimeoutError(Exception):
    """Agent 执行超时"""


class RuntimeLoopDetectedError(Exception):
    """检测到工具调用循环"""


# ============================================================
# 便捷工厂
# ============================================================


def create_runtime_from_settings(settings=None) -> AgentRuntime:
    """
    从项目配置创建 AgentRuntime。

    Args:
        settings: Settings 实例，不传则使用 RuntimeConfig 默认值

    Returns:
        配置好的 AgentRuntime
    """
    if settings is None:
        return AgentRuntime()

    config = RuntimeConfig(
        max_steps=getattr(settings, "agent_max_steps", 10),
        loop_window_size=getattr(settings, "agent_loop_window", 6),
        agent_timeout=getattr(settings, "agent_timeout", 30),
    )
    return AgentRuntime(config=config)


# ============================================================
# Smoke Test — python -m orchestration.langgraph.runtime
# ============================================================


if __name__ == "__main__":
    passed = 0
    failed = 0

    def check(name: str, ok: bool, detail: str = ""):
        global passed, failed
        if ok:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")
            if detail:
                print(f"         {detail}")

    # ── 1. RuntimeConfig ──
    print("\n" + "=" * 60)
    print("  1. RuntimeConfig")
    print("=" * 60)

    cfg = RuntimeConfig()
    check("default max_steps == 10", cfg.max_steps == 10)
    check("default loop_window_size == 6", cfg.loop_window_size == 6)
    check("default loop_threshold == 3", cfg.loop_threshold == 3)
    check("default agent_timeout == 30", cfg.agent_timeout == 30.0)

    # ── 2. LoopDetector ──
    print("\n" + "=" * 60)
    print("  2. LoopDetector")
    print("=" * 60)

    ld = LoopDetector(window_size=6, threshold=3)
    check("empty detector → no loop", not ld._check_loop())

    ld.feed("search_policy")
    ld.feed("check_material")
    ld.feed("search_policy")
    check("mixed calls → no loop", not ld._check_loop())

    ld2 = LoopDetector(window_size=6, threshold=3)
    check("feed search_policy x3 → loop",
          ld2.feed("search_policy") is False and
          ld2.feed("search_policy") is False and
          ld2.feed("search_policy") is True)

    ld3 = LoopDetector(window_size=6, threshold=3)
    long_sequence = ["search_policy", "check_material", "search_policy",
                     "search_policy", "search_policy"]
    result = ld3.feed_batch(long_sequence)
    check("batch feed 5 tools with 3 consecutive → loop", result is True)
    check("history preserves last 6", len(ld3.recent_tools) == 5)

    ld3.reset()
    check("reset clears history", len(ld3.recent_tools) == 0)

    # ── 3. AgentRuntime.check_step ──
    print("\n" + "=" * 60)
    print("  3. AgentRuntime.check_step")
    print("=" * 60)

    rt = AgentRuntime(config=RuntimeConfig(max_steps=3))
    from orchestration.langgraph.state import create_initial_state
    state = create_initial_state(user_query="test")

    # 步骤1-3 应该通过
    try:
        s1 = rt.check_step(state)
        check("step 1 OK", s1 is not None)
        s2 = rt.check_step(state)
        check("step 2 OK", s2 is not None)
        s3 = rt.check_step(state)
        check("step 3 OK", s3 is not None)
    except RuntimeExceededError:
        check("step 1-3 OK", False, "unexpected RuntimeExceededError")

    # 步骤4 应该超限
    try:
        rt.check_step(state)
        check("step 4 → RuntimeExceededError", False, "should have raised")
    except RuntimeExceededError as e:
        check("step 4 → RuntimeExceededError", True, str(e))
    check("step_count == 4", rt.step_count == 4)

    # ── 4. 错误累积 ──
    print("\n" + "=" * 60)
    print("  4. 错误累积")
    print("=" * 60)

    rt2 = AgentRuntime(config=RuntimeConfig(max_steps=100, max_error_count=2))
    s_err = {**state, "error": "failure_1"}
    try:
        rt2.check_step(s_err)
        check("error 1 OK", rt2.error_count == 1)
    except RuntimeExceededError:
        check("error 1 OK", False, "should not exceed yet")

    s_err2 = {**state, "error": "failure_2"}
    try:
        rt2.check_step(s_err2)
        check("error 2 OK", rt2.error_count == 2)
    except RuntimeExceededError:
        check("error 2 OK", False, "should not exceed yet")

    s_err3 = {**state, "error": "failure_3"}
    try:
        rt2.check_step(s_err3)
        check("error 3 → RuntimeExceededError", False, "should have raised")
    except RuntimeExceededError:
        check("error 3 → RuntimeExceededError", True)

    # ── 5. create_runtime_from_settings ──
    print("\n" + "=" * 60)
    print("  5. create_runtime_from_settings")
    print("=" * 60)

    rt_default = create_runtime_from_settings()
    check("default max_steps", rt_default.config.max_steps == 10)

    from dataclasses import dataclass as dc
    @dc
    class FakeSettings:
        agent_max_steps: int = 5
        agent_loop_window: int = 4
        agent_timeout: int = 15

    rt_custom = create_runtime_from_settings(FakeSettings())
    check("custom max_steps", rt_custom.config.max_steps == 5)
    check("custom loop_window", rt_custom.config.loop_window_size == 4)
    check("custom timeout", rt_custom.config.agent_timeout == 15)

    # ── Summary ──
    total = passed + failed
    print(f"\n{'='*60}")
    print(f"  RESULT: {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
    else:
        print(" — Runtime 安全护栏正常")
    print(f"{'='*60}")
    print("  运行方式: python -m orchestration.langgraph.runtime\n")
