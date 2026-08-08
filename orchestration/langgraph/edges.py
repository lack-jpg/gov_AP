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
                # 意图已识别 → 标记为 skipped 并跳过（避免 supervisor ↔ intent 死循环）
                if intent:
                    task["status"] = TaskStatus.SKIPPED.value
                    continue
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

    # 第四步：全部完成
    # 跨域查询（不动产/公积金）→ 先做 A2A 外部 Agent 协同（未执行过，或回调恢复待消费）
    if _needs_a2a(intent, state.get("user_query", "")) and (
        not state.get("a2a_tasks") or state.get("external_result")
    ):
        return NodeName.A2A_CHECK.value
    # 如果尚未合成最终答案 → 回supervisor合成
    # 如果已经有final_answer → governance安全检查
    if not state.get("final_answer", ""):
        return NodeName.SUPERVISOR.value
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
# Policy / Material / Workflow 后路由 → 检查是否还有pending任务
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
# Workflow 后路由 → 检查 A2A 需求
# ============================================================


def route_after_workflow(state: AgentState) -> str:
    """
    Workflow 节点之后的路由 — 检查是否需要 A2A 跨域调用。

    逻辑:
    - 如果 task_plan 全部完成且有 A2A 任务等待 → a2a_node
    - 如果 task_plan 全部完成且无 A2A → governance_node
    - 如果有 pending → route_after_supervisor
    - 如果有 waiting_task_id → 挂起等待（END）

    Args:
        state: 当前AgentState

    Returns:
        下一个节点名称
    """
    # 检查错误
    if state.get("error", ""):
        return NodeName.SUPERVISOR.value

    # 有等待中的 A2A 外部任务 → 挂起
    if state.get("waiting_task_id", ""):
        from langgraph.constants import END
        return END

    # 检查是否全部完成
    task_plan = state.get("task_plan", [])
    all_completed = all(
        t.get("status", "") in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.SKIPPED.value)
        for t in task_plan
    ) if task_plan else True

    if all_completed:
        # 检查是否需要 A2A 跨域调用
        intent = state.get("intent", "")
        user_query = state.get("user_query", "")
        if _needs_a2a(intent, user_query):
            return NodeName.A2A_CHECK.value
        # 尚未合成最终答案 → 先回 supervisor 汇总（含 workflow 等结果），否则直接治理
        if not state.get("final_answer", ""):
            return NodeName.SUPERVISOR.value
        return NodeName.GOVERNANCE.value

    return route_after_supervisor(state)


def _needs_a2a(intent: str, user_query: str) -> bool:
    """
    判断是否需要 A2A 跨域调用。

    Args:
        intent: 意图标签
        user_query: 用户查询

    Returns:
        True 如果需要调用外部 Agent
    """
    query_lower = user_query.lower()
    a2a_keywords = ("房产", "不动产", "房屋", "产权", "房子", "公积金", "住房基金")
    a2a_intents = ("property_service", "fund_query")

    if any(kw in query_lower for kw in a2a_keywords):
        return True
    if intent in a2a_intents:
        return True
    return False


# ============================================================
# A2A 后路由 → 继续流程或挂起
# ============================================================


def route_after_a2a(state: AgentState) -> str:
    """
    A2A 节点之后的路由。

    - 如果设置了 waiting_task_id → 挂起（END），等待外部回调
    - 如果 A2A 任务全部完成 → supervisor（汇总最终答案，含外部 Agent 结果）
    - 如果出错 → supervisor

    Args:
        state: 当前AgentState

    Returns:
        下一个节点名称
    """
    from langgraph.constants import END

    # 有等待中的外部任务 → 挂起
    if state.get("waiting_task_id", ""):
        return END

    # 错误处理
    if state.get("error", ""):
        return NodeName.SUPERVISOR.value

    # A2A 完成 → 回 supervisor 合成最终答案（含外部 Agent 数据），再走治理
    return NodeName.SUPERVISOR.value


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
