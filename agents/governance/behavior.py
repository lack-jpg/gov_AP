"""
governance.behavior - Agent behavior analysis: loop detection, anomaly monitoring

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement agent behavior monitoring and loop detection
"""
from __future__ import annotations

from collections import deque
from typing import Any

from orchestration.langgraph.state import AgentState
from tools.logger import get_logger

logger = get_logger(__name__)


class BehaviorAnalyzer:
    """
    Agent 行为分析器。

    监控指标:
        1. 工具调用循环: 窗口内同一 tool 连续调用 N 次
        2. 步数过多: 超出预期步数
        3. 重复输出: 连续两次输出相同或高度相似
        4. Token 消耗异常: 输入+输出 Token 过多
    """

    def __init__(self):
        self._tool_history: deque[str] = deque(maxlen=10)

    def analyze(self, state: AgentState) -> dict[str, Any]:
        """
        分析当前 State 中的 Agent 行为。

        Args:
            state: 当前 AgentState

        Returns:
            {
                "anomaly_detected": bool,
                "reason": str,
                "loop_detected": bool,
                "loop_tool": str | None,
                "excessive_steps": bool,
                "current_step_count": int,
            }
        """
        result: dict[str, Any] = {
            "anomaly_detected": False,
            "reason": "",
            "loop_detected": False,
            "loop_tool": None,
            "excessive_steps": False,
            "current_step_count": 0,
        }

        # 1. 工具调用循环检测
        tool_calls = state.get("tool_calls", [])
        tool_names = [
            tc.get("tool_name", "") if isinstance(tc, dict) else getattr(tc, "tool_name", "")
            for tc in tool_calls
        ]
        for name in tool_names:
            self._tool_history.append(name)

        if self._detect_loop():
            result["anomaly_detected"] = True
            result["reason"] = "检测到工具调用循环"
            result["loop_detected"] = True
            result["loop_tool"] = self._tool_history[-1]

        # 2. mcp_history 中的调用统计
        mcp_history = state.get("mcp_history", [])
        result["current_step_count"] = len(mcp_history)

        if len(mcp_history) > 20:
            result["anomaly_detected"] = True
            result["reason"] = f"MCP 调用步数过多 ({len(mcp_history)})"
            result["excessive_steps"] = True

        # 3. Token 消耗检查
        metrics = state.get("execution_metrics", {})
        if isinstance(metrics, dict):
            total_tokens = metrics.get("input_tokens", 0) + metrics.get("output_tokens", 0)
            if total_tokens > 100000:
                result["anomaly_detected"] = True
                result["reason"] = f"Token 消耗过大 ({total_tokens})"

        if result["anomaly_detected"]:
            logger.warning("[BehaviorAnalyzer] 异常: {}", result["reason"])

        return result

    def _detect_loop(self, window: int = 6, threshold: int = 3) -> bool:
        """
        滑动窗口循环检测。

        Args:
            window: 窗口大小
            threshold: 连续相同 tool 次数阈值

        Returns:
            True 表示检测到循环
        """
        if len(self._tool_history) < threshold:
            return False
        recent = list(self._tool_history)[-threshold:]
        return len(set(recent)) == 1

    def reset(self) -> None:
        """重置分析器"""
        self._tool_history.clear()
