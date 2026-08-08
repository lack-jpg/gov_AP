"""
langgraph.graph - StateGraph builder: define nodes, edges, and conditional routing

Author: le
Date: 2026/7/29
Version: 0.1
Task: Build the full LangGraph StateGraph with all agent nodes and transitions
"""
from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from agents.supervisor.agent import SupervisorAgent
from tools.logger import get_logger
from orchestration.langgraph.edges import (
    route_after_supervisor,
    route_after_intent,
    route_after_specialist,
    route_after_workflow,
    route_after_a2a,
    route_after_governance,
)
from orchestration.langgraph.nodes import (
    supervisor_node,
    intent_node,
    policy_node,
    material_node,
    workflow_node,
    a2a_node,
    governance_node,
)
from orchestration.langgraph.state import AgentState

logger = get_logger(__name__)


# ============================================================
# Graph Builder
# ============================================================


def build_graph(
    *,
    llm: Optional[BaseChatModel] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    supervisor: Optional[SupervisorAgent] = None,
    mcp_client=None,
    a2a_connector=None,
) -> StateGraph:
    """
    构建完整的Agent工作流 StateGraph。

    Graph结构:

        START
          |
     supervisor_node ─────────────────────────────┐
          |                                        │
          v                                        │
     intent_node ──→ supervisor_node (回传结果)     │
          |                                        │
          v                                        │
     +──────────+                                  │
     |          |                                  │
     v          v                                  │
  policy    material                               │
  _node     _node                                  │
     |          |                                  │
     +────┬─────+                                  │
          |                                        │
          v                                        │
     workflow_node                                 │
          |                                        │
          v                                        │
     a2a_node ──→ (waiting/END)                    │
          |                                        │
          v                                        │
     governance_node ──────────────────────────────┘
          |
          v
         END

    Args:
        llm: LangChain ChatModel实例，注入所有需要LLM的节点
        checkpointer: LangGraph Checkpointer（PostgreSQL），
                      用于A2A异步任务挂起/恢复和长流程持久化
        supervisor: 预构建的SupervisorAgent（可选复用），
                    不传则用llm自动构建
        mcp_client: MCPClient 实例，注入 policy/material/workflow 节点。
                    不传则使用 stub fallback。
        a2a_connector: A2AConnector 实例，注入 a2a_node。
                       不传则使用 stub fallback。

    Returns:
        已编译的LangGraph StateGraph（compiled graph）
    """
    # 预构建supervisor（如果没有传入）
    if supervisor is None:
        supervisor = SupervisorAgent(llm=llm)

    # ── 创建 StateGraph ──
    graph = StateGraph(AgentState)

    # ── 注册节点 ──
    # 注意：LangGraph 要求节点函数必须是 async def，
    # 不能使用 sync lambda 返回 coroutine（Python 不支持 async lambda）
    async def _supervisor_wrapper(state: AgentState) -> AgentState:
        return await supervisor_node(state, supervisor=supervisor, llm=llm)

    async def _intent_wrapper(state: AgentState) -> AgentState:
        return await intent_node(state, llm=llm)

    async def _policy_wrapper(state: AgentState) -> AgentState:
        return await policy_node(state, llm=llm, mcp_client=mcp_client)

    async def _material_wrapper(state: AgentState) -> AgentState:
        return await material_node(state, llm=llm, mcp_client=mcp_client)

    async def _workflow_wrapper(state: AgentState) -> AgentState:
        return await workflow_node(state, llm=llm, mcp_client=mcp_client)

    async def _governance_wrapper(state: AgentState) -> AgentState:
        return await governance_node(state, llm=llm)

    async def _a2a_wrapper(state: AgentState) -> AgentState:
        return await a2a_node(state, llm=llm, a2a_connector=a2a_connector, checkpointer=checkpointer)

    graph.add_node("supervisor_node", _supervisor_wrapper)
    graph.add_node("intent_node", _intent_wrapper)
    graph.add_node("policy_node", _policy_wrapper)
    graph.add_node("material_node", _material_wrapper)
    graph.add_node("workflow_node", _workflow_wrapper)
    graph.add_node("a2a_node", _a2a_wrapper)
    graph.add_node("governance_node", _governance_wrapper)

    # ── 注册边 ──

    # START → supervisor
    graph.add_edge(START, "supervisor_node")

    # supervisor → 条件路由（根据task_plan决定下一个节点）
    graph.add_conditional_edges(
        "supervisor_node",
        route_after_supervisor,
        {
            "intent_node": "intent_node",
            "policy_node": "policy_node",
            "material_node": "material_node",
            "workflow_node": "workflow_node",
            "a2a_node": "a2a_node",
            "governance_node": "governance_node",
            "supervisor_node": "supervisor_node",  # 可能需要重新规划
        },
    )

    # intent → 回到supervisor（基于识别的意图重新规划）
    graph.add_edge("intent_node", "supervisor_node")

    # policy/material → 条件路由（检查是否完成或需要继续）
    for node in ("policy_node", "material_node"):
        graph.add_conditional_edges(
            node,
            route_after_specialist,
            {
                "intent_node": "intent_node",
                "policy_node": "policy_node",
                "material_node": "material_node",
                "workflow_node": "workflow_node",
                "a2a_node": "a2a_node",
                "governance_node": "governance_node",
                "supervisor_node": "supervisor_node",
            },
        )

    # workflow → 条件路由（检查 A2A 需求）
    graph.add_conditional_edges(
        "workflow_node",
        route_after_workflow,
        {
            "a2a_node": "a2a_node",
            "governance_node": "governance_node",
            "supervisor_node": "supervisor_node",
            "policy_node": "policy_node",
            "material_node": "material_node",
            "intent_node": "intent_node",
            END: END,
        },
    )

    # a2a → 条件路由（挂起等待或继续）
    graph.add_conditional_edges(
        "a2a_node",
        route_after_a2a,
        {
            "governance_node": "governance_node",
            "supervisor_node": "supervisor_node",
            END: END,
        },
    )

    # governance → 条件路由（通过则END，有问题则回supervisor）
    graph.add_conditional_edges(
        "governance_node",
        route_after_governance,
        {
            "supervisor_node": "supervisor_node",
            END: END,
        },
    )

    # ── 编译 ──
    if checkpointer is not None:
        graph = graph.compile(checkpointer=checkpointer)
    else:
        graph = graph.compile()

    logger.info(
        "LangGraph compiled successfully (checkpointer=%s, llm=%s)",
        type(checkpointer).__name__ if checkpointer else "None",
        type(llm).__name__ if llm else "None",
    )

    return graph


# ============================================================
# 便捷工厂 — 创建带默认配置的Graph
# ============================================================


def create_default_graph() -> StateGraph:
    """
    创建默认配置的Graph（无LLM，纯stub模式）。

    所有Agent节点使用stub实现：
    - Intent: 关键词匹配
    - Policy: 静态模板回答
    - Material: 空审核（默认通过）
    - Workflow: 模拟办件ID

    用途：开发调试、单元测试、CI pipeline

    Returns:
        编译好的StateGraph
    """
    return build_graph(llm=None, checkpointer=None)
