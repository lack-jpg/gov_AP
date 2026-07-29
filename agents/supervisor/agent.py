"""
supervisor.agent - Supervisor Agent core: task understanding, decomposition, routing

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement Supervisor Agent main orchestration logic
"""
from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel

from agents.supervisor.planner import Planner
from agents.supervisor.router import Router
from orchestration.langgraph.state import (
    AgentName,
    AgentState,
    NodeName,
    Task,
    TaskStatus,
    RiskLevel,
    create_initial_state,
    set_intent,
    add_task,
    set_final_answer,
    set_error,
    update_current_agent,
    transition_to,
)


# ============================================================
# SupervisorAgent
# ============================================================


class SupervisorAgent:
    """
    Supervisor Agent — 多智能体系统的大脑。

    职责（不包含业务逻辑）：
    1. 任务理解：接收用户输入，评估当前state
    2. 任务拆解：调用Planner生成子任务序列
    3. Agent路由：调用Router为每个子任务选择执行者
    4. 状态管理：更新AgentState，决定流程走向
    5. 异常处理：执行失败时重新规划或降级

    禁止：
    - 直接回答业务问题
    - 直接调用MCP工具
    - 包含业务规则

    使用方式:
        supervisor = SupervisorAgent(llm)
        state = await supervisor.orchestrate(state)
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        """
        Args:
            llm: LangChain ChatModel。如果为None，Planner和Router
                 使用纯规则模式（不依赖LLM），适合测试或无LLM环境。
        """
        self._planner = Planner(llm=llm)
        self._router = Router(llm=llm)

    # ── 公开接口 ──

    async def orchestrate(self, state: AgentState) -> AgentState:
        """
        Supervisor主入口。

        根据当前State的阶段执行不同的编排逻辑：
        - 初次进入：初始化，生成task_plan
        - 已有意图：根据意图更新task_plan
        - 执行中：检查进度，可能需要重新规划
        - 全部完成：汇总结果，生成final_answer

        Args:
            state: 当前AgentState

        Returns:
            更新后的AgentState，包含task_plan和路由信息
        """
        state = update_current_agent(state, AgentName.SUPERVISOR)
        state = transition_to(state, NodeName.SUPERVISOR)

        task_plan = state.get("task_plan", [])
        intent = state.get("intent", "")
        error = state.get("error", "")

        # 场景1: 执行出错 → 重新规划
        if error:
            return await self._handle_error(state)

        # 场景2: 全部任务完成 → 汇总
        if task_plan and self._all_completed(task_plan):
            return await self._synthesize(state)

        # 场景3: 已有部分任务在执行/完成 → 检查是否需要补充
        if task_plan and self._has_pending(task_plan):
            return state  # 继续执行，不需要重新规划

        # 场景4: 初次进入或无计划 → 生成plan
        return await self._plan_and_route(state)

    async def handle_intent_result(self, state: AgentState, intent_label: str) -> AgentState:
        """
        处理Intent Agent返回的意图识别结果。

        根据意图更新state并重新规划task_plan。

        Args:
            state: 当前State
            intent_label: Intent Agent识别出的意图标签

        Returns:
            更新后的State
        """
        from orchestration.langgraph.state import IntentResult

        intent_result = IntentResult(
            label=intent_label,
            label_name="",
            confidence=0.9,
            source="bert",
        )
        state = set_intent(state, intent_result)

        # 基于意图重新规划
        tasks = await self._planner.plan(state)
        for task in tasks:
            state = add_task(state, task)
            # 为每个任务分配Agent
            agent = await self._router.route(task)
            # 更新task中的agent字段（如果LLM路由与规则不同）
            if agent != task.agent:
                task.agent = agent

        return state

    async def handle_error_and_replan(self, state: AgentState, error_message: str) -> AgentState:
        """
        处理执行错误：记录错误 → 重新规划 → 跳过失败任务。

        Args:
            state: 当前State
            error_message: 错误描述

        Returns:
            更新后的State
        """
        state = set_error(state, error_message)
        return await self._handle_error(state)

    # ── 内部 ──

    async def _plan_and_route(self, state: AgentState) -> AgentState:
        """生成task_plan并为每个任务确定Agent"""
        tasks = await self._planner.plan(state)

        if not tasks:
            # 无法拆解 → 标记为高风险
            return {**state, "risk_level": RiskLevel.HIGH.value}

        for task in tasks:
            state = add_task(state, task)

        return state

    async def _handle_error(self, state: AgentState) -> AgentState:
        """错误恢复：重新规划，跳过失败任务"""
        error = state.get("error", "unknown error")
        retry_count = state.get("retry_count", 0)

        if retry_count >= 3:
            # 重试次数耗尽 → 返回错误给用户
            return await self._synthesize(state)

        tasks = await self._planner.replan_on_error(state, error)
        # 清除旧的task_plan，注入新的
        # 注意：这里需要操作原始state的task_plan
        # 实际上LangGraph的reducer会处理合并
        new_state: AgentState = {**state}  # type: ignore[misc]
        new_state["task_plan"] = [t.model_dump() for t in tasks]
        return new_state

    async def _synthesize(self, state: AgentState) -> AgentState:
        """
        汇总所有Agent结果，生成最终回答。

        优先级：
        1. policy_result中的answer（有证据支撑）
        2. material_result中的审核结果
        3. 现有task_plan的完成情况
        """
        parts: list[str] = []

        policy = state.get("policy_result", {})
        if isinstance(policy, dict) and policy.get("answer"):
            parts.append(policy["answer"])

        material = state.get("material_result", {})
        if isinstance(material, dict):
            if material.get("passed") is False:
                missing = material.get("missing", [])
                if missing:
                    parts.append(f"\n需要注意，以下材料尚未准备：{'、'.join(missing)}")

        task_plan = state.get("task_plan", [])
        if task_plan:
            completed = sum(1 for t in task_plan if t.get("status") == TaskStatus.COMPLETED.value)
            failed = sum(1 for t in task_plan if t.get("status") == TaskStatus.FAILED.value)
            if failed > 0:
                parts.append(f"\n有 {failed} 个步骤未能完成，建议联系人工客服。")

        final_answer = "\n".join(parts) if parts else "抱歉，未能处理您的请求，请稍后重试或联系人工客服。"
        return set_final_answer(state, final_answer)

    # ── 状态检查 ──

    @staticmethod
    def _all_completed(task_plan: list[dict]) -> bool:
        """检查是否所有任务都已完成或失败"""
        if not task_plan:
            return False
        for t in task_plan:
            status = t.get("status", "")
            if status not in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.SKIPPED.value):
                return False
        return True

    @staticmethod
    def _has_pending(task_plan: list[dict]) -> bool:
        """检查是否还有待执行的任务"""
        return any(
            t.get("status") in (TaskStatus.PENDING.value, TaskStatus.RUNNING.value)
            for t in task_plan
        )
