"""
governance.optimizer - Auto-optimization: analyze traces, suggest prompt/workflow improvements

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement agent optimization based on evaluation feedback
"""
from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel

from tools.logger import get_logger

logger = get_logger(__name__)


class Optimizer:
    """
    自动优化器 — 基于 Trace 和 Evaluation 结果生成优化建议。

    分析维度:
        1. Prompt 优化: 分析失败 case，建议 Prompt 改进
        2. Workflow 优化: 分析执行路径，建议流程精简
        3. Agent Routing 优化: 分析路由错误，建议调整路由规则

    当前实现: 基于规则的启发式分析
    TODO: 接入 LLM 做深度分析和自动 Prompt 生成
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._llm = llm

    async def analyze(self, traces: list[dict]) -> list[dict]:
        """
        分析 Trace 历史，生成优化建议。

        Args:
            traces: 历史 Trace 记录列表

        Returns:
            优化建议列表
        """
        suggestions: list[dict] = []

        if not traces:
            return suggestions

        # 1. 失败率分析
        failed = [t for t in traces if t.get("status") in ("failed", "error", "timeout")]
        if failed:
            fail_rate = len(failed) / len(traces)
            if fail_rate > 0.2:
                suggestions.append({
                    "type": "workflow",
                    "target": "error_handling",
                    "severity": "high",
                    "suggestion": f"任务失败率 {fail_rate:.0%}，建议加强错误处理和 retry 机制",
                    "failed_count": len(failed),
                })

        # 2. 步数分析
        steps = [t.get("step_count", 0) for t in traces if t.get("step_count", 0) > 0]
        if steps:
            avg_steps = sum(steps) / len(steps)
            if avg_steps > 5:
                suggestions.append({
                    "type": "workflow",
                    "target": "task_planning",
                    "severity": "medium",
                    "suggestion": f"平均执行步数 {avg_steps:.1f}，建议优化 Supervisor 的任务拆解策略",
                    "avg_steps": avg_steps,
                })

        # 3. 延迟分析
        latencies = [t.get("latency_ms", 0) for t in traces if t.get("latency_ms", 0) > 0]
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            if avg_latency > 5000:
                suggestions.append({
                    "type": "performance",
                    "target": "mcp_calling",
                    "severity": "medium",
                    "suggestion": f"平均延迟 {avg_latency:.0f}ms，建议优化 MCP 调用或增加缓存",
                    "avg_latency_ms": avg_latency,
                })

        # 4. Tool 使用分析
        tool_usage: dict[str, int] = {}
        for t in traces:
            tool_name = t.get("tool_name", "")
            if tool_name:
                tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1

        for tool, count in tool_usage.items():
            if count > 10:
                suggestions.append({
                    "type": "performance",
                    "target": "caching",
                    "severity": "low",
                    "suggestion": f"'{tool}' 被频繁调用 ({count}次)，考虑增加结果缓存",
                    "tool": tool,
                    "count": count,
                })

        if suggestions:
            logger.info("生成了 {} 条优化建议", len(suggestions))
        else:
            logger.info("未发现需要优化的项")

        return suggestions

    async def suggest_prompt_improvement(self, failure_cases: list[dict]) -> str:
        """
        基于失败 case 建议 Prompt 改进。

        Args:
            failure_cases: 失败的用例列表

        Returns:
            Prompt 优化建议文本
        """
        if not failure_cases:
            return "无失败用例"

        if self._llm is not None:
            # TODO: LLM 深度分析
            pass

        # 启发式分析
        intent_errors = sum(
            1 for c in failure_cases
            if c.get("error_type") == "intent_mismatch"
        )
        policy_errors = sum(
            1 for c in failure_cases
            if c.get("error_type") == "policy_not_found"
        )
        total = len(failure_cases)

        parts: list[str] = [f"共 {total} 个失败用例，建议："]

        if intent_errors > 0:
            parts.append(
                f"- 意图识别错误 {intent_errors} 次，"
                f"建议在 INTENT_CLASSIFICATION_PROMPT 中增加 more specific examples"
            )
        if policy_errors > 0:
            parts.append(
                f"- 政策未找到 {policy_errors} 次，"
                f"建议检查知识库索引是否覆盖相关领域"
            )

        return "\n".join(parts)
