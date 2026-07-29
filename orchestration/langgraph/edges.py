"""
langgraph.edges - Conditional edge logic: routing rules between agent nodes

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement conditional routing edges for agent node transitions
"""
from __future__ import annotations

from orchestration.langgraph.state import (
    AgentName,
    AgentState,
    NodeName,
    TaskStatus,
    RiskLevel,
)


# ============================================================
# 主路由 — Supervisor → 下一个节点
# ============================================================


def route_after_supervisor(state: AgentState) -> str:
    """
    Supervisor节点之后的路由决策。

    根据 task_plan 和当前进度决定下一个节点：
    - 如果没有plan → intent（先识别意图）
    - 如果有pending的intent任务 → intent
    - 如果有pending的policy任务 → policy
    - 如果有pending的material任务 → material
    - 如果有pending的workflow任务 → workflow
    - 如果全部完成 → governance（安全检查后结束）

    Args:
        state: 当前AgentState

    Returns:
        下一个节点名称 (NodeName枚举值)
    """
    task_plan = state.get("task_plan", [])
    intent = state.get("intent", "")

    # 第一步：没有意图 → 先识别
    if not intent:
        return NodeName.INTENT.value

    # 第二步：没有计划 → 回到supervisor做规划
    if not task_plan:
        return NodeName.SUPERVISOR.value

    # 第三步：遍历task_plan，找第一个pending的任务
    for task in task_plan:
        status = task.get("status", "pending")
        if status == TaskStatus.PENDING.value:
            task_type = task.get("type", "")
            agent = task.get("agent", "")

            # 按agent字段路由
            if agent == AgentName.INTENT.value or task_type == "classify_intent":
                return NodeName.INTENT.value
            elif agent == AgentName.POLICY.value:
                return NodeName.POLICY.value
            elif agent == AgentName.MATERIAL.value:
                return NodeName.MATERIAL.value
            elif agent == AgentName.WORKFLOW.value:
                return NodeName.WORKFLOW.value
            else:
                # 按 task_type 猜测
                if "policy" in task_type or "search" in task_type:
                    return NodeName.POLICY.value
                elif "material" in task_type or "check" in task_type or "extract" in task_type:
                    return NodeName.MATERIAL.value
                elif "case" in task_type or "workflow" in task_type or "create" in task_type:
                    return NodeName.WORKFLOW.value

    # 第四步：全部完成 → governance 安全检查
    return NodeName.GOVERNANCE.value


# ============================================================
# Intent 后路由 → Supervisor（回传结果继续规划）
# ============================================================


def route_after_intent(state: AgentState) -> str:
    """
    Intent Agent之后的路由。

    无论什么情况都回到Supervisor做二次规划（基于识别出的意图）。

    Args:
        state: 当前AgentState

    Returns:
        NodeName.SUPERVISOR.value
    """
    return NodeName.SUPERVISOR.value


# ============================================================
# Policy / Material 后路由 → 检查是否还有pending任务
# ============================================================


def route_after_specialist(state: AgentState) -> str:
    """
    专业Agent（Policy/Material/Workflow）之后的路由。

    检查task_plan是否全部完成：
    - 如果还有pending → 使用route_after_supervisor继续
    - 如果全部完成 → governance
    - 如果出错 → supervisor（重新规划）

    Args:
        state: 当前AgentState

    Returns:
        下一个节点名称
    """
    # 先检查错误
    if state.get("error", ""):
        return NodeName.SUPERVISOR.value

    # 检查风险等级
    risk = state.get("risk_level", "")
    if risk in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value):
        return NodeName.GOVERNANCE.value

    # 继续正常路由
    return route_after_supervisor(state)


# ============================================================
# Governance 后路由
# ============================================================


def route_after_governance(state: AgentState) -> str:
    """
    Governance Agent之后的路由。

    - 如果被拦截（blocked） → 直接结束
    - 如果有错误需要重试 → 回到supervisor
    - 如果通过 → 检查是否有A2A外部任务在等待

    Args:
        state: 当前AgentState

    Returns:
        "__end__" 或下一个节点名称
    """
    from langgraph.constants import END

    safety = state.get("safety_check", {})
    if isinstance(safety, dict) and safety.get("blocked", False):
        return END

    # A2A pending task → 挂起等待
    if state.get("waiting_task_id", ""):
        return END  # 由外部callback恢复

    # 有错误需要重试
    error = state.get("error", "")
    retry_count = state.get("retry_count", 0)
    if error and retry_count < 3:
        return NodeName.SUPERVISOR.value

    return END


# ============================================================
# 起始路由 — 根据输入决定第一个节点
# ============================================================


def route_on_start(state: AgentState) -> str:
    """
    图起始路由。

    根据用户输入和当前状态决定第一个执行节点：
    - 正常流程 → supervisor

    Args:
        state: 初始AgentState

    Returns:
        第一个节点名称
    """
    # 正常流程从supervisor开始
    return NodeName.SUPERVISOR.value
