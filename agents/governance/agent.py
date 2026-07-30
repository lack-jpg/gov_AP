"""
governance.agent - Governance Agent core: security check, loop detection, behavior monitoring

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement Governance Agent for out-of-band safety and monitoring
"""
from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel

from agents.governance.security import SecurityChecker
from agents.governance.behavior import BehaviorAnalyzer
from agents.governance.optimizer import Optimizer
from orchestration.langgraph.state import (
    AgentState,
    GuardrailResult,
    RiskLevel,
    ExecutionMetrics,
)
from tools.logger import get_logger

logger = get_logger(__name__)


class GovernanceAgent:
    """
    Governance Agent — 旁路安全治理。

    职责（不参与业务回答）：
    1. 安全检查：PII 检测、注入检测、敏感词过滤 ← SecurityChecker
    2. 行为分析：循环检测、异常行为识别 ← BehaviorAnalyzer
    3. 自动优化：Trace 分析、优化建议生成 ← Optimizer

    使用方式:
        agent = GovernanceAgent()
        result = await agent.check(state)
        # GuardrailResult(passed=True, blocked=False, ...)
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._security = SecurityChecker()
        self._behavior = BehaviorAnalyzer()
        self._optimizer = Optimizer(llm=llm)

    async def check(self, state: AgentState) -> GuardrailResult:
        """
        执行完整的安全检查。

        检查顺序: 输入安全 → 输出安全 → 行为分析

        Args:
            state: 当前 AgentState

        Returns:
            GuardrailResult（含 passed / blocked / pii_detected / injection_detected 等）
        """
        user_query = state.get("user_query", "")
        final_answer = state.get("final_answer", "")

        # 1. 输入安全检查
        input_result = self._security.check_input(user_query)
        if input_result.blocked:
            logger.warning("输入被拦截: {}", input_result.reason)
            return input_result

        # 2. 输出安全检查（如果有最终答案）
        if final_answer:
            output_result = self._security.check_output(final_answer)
            if output_result.blocked:
                logger.warning("输出被拦截: {}", output_result.reason)
                return output_result

        # 3. 行为分析
        behavior_result = self._behavior.analyze(state)
        if behavior_result.get("anomaly_detected"):
            logger.warning("检测到异常行为: {}", behavior_result.get("reason", "unknown"))

        # 综合结果
        return GuardrailResult(
            passed=input_result.passed and not behavior_result.get("anomaly_detected", False),
            pii_detected=input_result.pii_detected,
            injection_detected=input_result.injection_detected,
            sensitive_words=input_result.sensitive_words,
            blocked=input_result.blocked,
            reason=input_result.reason,
        )

    async def process(self, state: AgentState) -> AgentState:
        """
        LangGraph 节点接口。

        Args:
            state: 当前 AgentState

        Returns:
            更新后的 AgentState（safety_check 字段已设置）
        """
        result = await self.check(state)
        state["safety_check"] = result.model_dump()

        if result.blocked:
            state["risk_level"] = RiskLevel.HIGH.value
        elif result.pii_detected:
            state["risk_level"] = RiskLevel.MEDIUM.value

        return state

    async def generate_optimization_suggestions(
        self,
        traces: list[dict],
    ) -> list[dict]:
        """
        基于 Trace 历史生成优化建议。

        Args:
            traces: 历史 Trace 记录列表

        Returns:
            优化建议列表 [{"target": "...", "suggestion": "..."}, ...]
        """
        return await self._optimizer.analyze(traces)
