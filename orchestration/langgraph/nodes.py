"""
langgraph.nodes - LangGraph node functions: each node wraps an Agent invocation

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement node functions (supervisor_node, intent_node, policy_node, etc.)
"""
from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel

from agents.supervisor.agent import SupervisorAgent
from tools.logger import get_logger, log_agent_call, log_mcp_call
from orchestration.langgraph.state import (
    AgentName,
    AgentState,
    IntentResult,
    MaterialCheckResult,
    MCPCallRecord,
    MCPCallStatus,
    NodeName,
    PolicyResult,
    TaskStatus,
    update_current_agent,
    transition_to,
    set_error,
    add_evidence,
    record_mcp_call,
)

logger = get_logger(__name__)


# ============================================================
# Supervisor Node
# ============================================================


async def supervisor_node(
    state: AgentState,
    supervisor: Optional[SupervisorAgent] = None,
    llm: Optional[BaseChatModel] = None,
) -> AgentState:
    """
    Supervisor节点 — 全局任务编排。

    每次进入此节点都会触发Supervisor的orchestrate逻辑：
    生成/更新task_plan → 路由 → 决定下一个Agent。

    Args:
        state: 当前AgentState
        supervisor: 已构建的SupervisorAgent实例（可选，复用）
        llm: LLM实例（如果supervisor未传入则用此构建）

    Returns:
        更新后的AgentState
    """
    if supervisor is None:
        supervisor = SupervisorAgent(llm=llm)

    state = update_current_agent(state, AgentName.SUPERVISOR)
    state = transition_to(state, NodeName.SUPERVISOR)

    try:
        state = await supervisor.orchestrate(state)
    except Exception as e:
        logger.error(f"Supervisor orchestrate failed: {e}", exc_info=True)
        state = set_error(state, f"Supervisor orchestrate error: {e}")

    return state


# ============================================================
# Intent Node
# ============================================================


async def intent_node(
    state: AgentState,
    llm: Optional[BaseChatModel] = None,
) -> AgentState:
    """
    Intent节点 — 意图识别。

    当前为stub实现（返回默认意图）。
    完整实现需要接入BERT模型 + LLM fallback。

    Args:
        state: 当前AgentState
        llm: LLM实例

    Returns:
        更新后的AgentState
    """
    state = update_current_agent(state, AgentName.INTENT)
    state = transition_to(state, NodeName.INTENT)

    try:
        user_query = state.get("user_query", "")

        # TODO: 替换为真实的BERT分类器 + LLM fallback
        # from agents.intent.classifier import IntentClassifier
        # from agents.intent.agent import IntentAgent
        # agent = IntentAgent(classifier=classifier, llm=llm)
        # result = await agent.classify(user_query)

        # Stub: 简单的关键词匹配
        intent_label = _stub_intent_classify(user_query)

        intent_result = IntentResult(
            label=intent_label,
            label_name="",
            confidence=0.85,
            source="stub",
        )
        from orchestration.langgraph.state import set_intent
        state = set_intent(state, intent_result)

    except Exception as e:
        logger.error(f"Intent classification failed: {e}", exc_info=True)
        state = set_error(state, f"Intent classification error: {e}")

    return state


def _stub_intent_classify(query: str) -> str:
    """临时意图分类stub — 后续替换为BERT模型"""
    query_lower = query.lower()
    if any(kw in query_lower for kw in ("餐馆", "餐饮", "饭店", "餐厅", "食品")):
        return "restaurant_license"
    if any(kw in query_lower for kw in ("公司", "企业", "注册", "营业执照")):
        return "business_register"
    if any(kw in query_lower for kw in ("公积金", "住房")):
        return "fund_query"
    if any(kw in query_lower for kw in ("房产", "不动产", "房屋", "产权")):
        return "property_service"
    return "business_license"  # 默认


# ============================================================
# Policy Node
# ============================================================


async def policy_node(
    state: AgentState,
    llm: Optional[BaseChatModel] = None,
) -> AgentState:
    """
    Policy节点 — 政策检索。

    当前为stub实现（返回静态政策信息）。
    完整实现需要接入RAG管线：embedding → Milvus → BM25 → Reranker → LLM生成。

    Args:
        state: 当前AgentState
        llm: LLM实例

    Returns:
        更新后的AgentState
    """
    state = update_current_agent(state, AgentName.POLICY)
    state = transition_to(state, NodeName.POLICY)

    try:
        user_query = state.get("user_query", "")
        intent = state.get("intent", "")

        # TODO: 替换为真实的RAG管线
        # from rag.embedding import EmbeddingEngine
        # from rag.retriever import HybridRetriever
        # from rag.reranker import Reranker
        # from rag.generator import Generator

        # Stub: 返回静态政策信息
        stub_answer = _stub_policy_search(intent, user_query)

        policy_result = PolicyResult(
            answer=stub_answer["answer"],
            evidence=[],
            confidence=0.9,
        )
        state["policy_result"] = policy_result.model_dump()

        # 可选：记录MCP调用
        mcp = MCPCallRecord(
            trace_id=state["trace_id"],
            server_name="policy_server",
            tool_name="search_policy",
            input_args={"query": user_query, "top_k": 5},
            output_result={"policy_found": True},
            latency_ms=200.0,
            status=MCPCallStatus.SUCCESS,
        )
        state = record_mcp_call(state, mcp)

    except Exception as e:
        logger.error(f"Policy search failed: {e}", exc_info=True)
        state = set_error(state, f"Policy search error: {e}")

    return state


def _stub_policy_search(intent: str, query: str) -> dict:
    """临时政策查询stub — 后续替换为RAG管线"""
    if "restaurant" in intent or "餐馆" in query or "餐饮" in query:
        return {
            "answer": (
                "开办餐馆需要以下手续：\n"
                "1. 营业执照 — 到当地市场监管局办理\n"
                "2. 食品经营许可证 — 到食品药品监督管理部门办理\n"
                "3. 消防安全检查合格证 — 到消防部门办理\n"
                "4. 环保审批 — 根据当地环保要求\n\n"
                "基本材料：身份证、经营场所证明（租赁合同或房产证）、"
                "从业人员健康证、食品安全管理制度。"
            ),
        }
    elif "business" in intent or "公司" in query or "注册" in query:
        return {
            "answer": (
                "企业注册基本流程：\n"
                "1. 名称预先核准\n"
                "2. 提交设立登记申请\n"
                "3. 领取营业执照\n"
                "所需材料：法人身份证、经营场所证明、公司章程、股东决议。"
            ),
        }
    elif "fund" in intent or "公积金" in query:
        return {
            "answer": (
                "公积金查询方式：\n"
                "1. 登录当地住房公积金管理中心官网\n"
                "2. 拨打12329住房公积金热线\n"
                "3. 持身份证到服务大厅自助终端查询"
            ),
        }
    else:
        return {
            "answer": (
                "根据您的需求，建议准备以下基础材料：\n"
                "1. 本人有效身份证件\n"
                "2. 相关申请表（可在政务大厅领取或网上下载）\n"
                "3. 根据具体事项可能需要补充材料\n\n"
                "建议先确认具体办理事项后再查询详细要求。"
            ),
        }


# ============================================================
# Material Node
# ============================================================


async def material_node(
    state: AgentState,
    llm: Optional[BaseChatModel] = None,
) -> AgentState:
    """
    Material节点 — 材料审核。

    当前为stub实现（返回空审核结果）。
    完整实现需要接入OCR + 实体抽取 + 规则校验。

    Args:
        state: 当前AgentState
        llm: LLM实例

    Returns:
        更新后的AgentState
    """
    state = update_current_agent(state, AgentName.MATERIAL)
    state = transition_to(state, NodeName.MATERIAL)

    try:
        # TODO: 替换为真实的Material Agent
        # from agents.material.agent import MaterialAgent
        # agent = MaterialAgent(llm=llm)
        # result = await agent.review(...)

        result = MaterialCheckResult(
            passed=True,
            missing=[],
            warnings=["当前为stub模式，未进行真实材料审核"],
        )
        state["material_result"] = result.model_dump()

        # 标记task_plan中对应的material任务为完成
        task_plan = state.get("task_plan", [])
        updated_plan: list[dict] = []
        for t in task_plan:
            agent = t.get("agent", "")
            if agent == AgentName.MATERIAL.value and t.get("status") == TaskStatus.PENDING.value:
                t = {**t, "status": TaskStatus.COMPLETED.value}
            updated_plan.append(t)
        state["task_plan"] = updated_plan

    except Exception as e:
        logger.error(f"Material check failed: {e}", exc_info=True)
        state = set_error(state, f"Material check error: {e}")

    return state


# ============================================================
# Workflow Node
# ============================================================


async def workflow_node(
    state: AgentState,
    llm: Optional[BaseChatModel] = None,
) -> AgentState:
    """
    Workflow节点 — 流程执行。

    当前为stub实现（返回模拟办件结果）。
    完整实现需要通过MCP Client调用create_case和query_status。

    Args:
        state: 当前AgentState
        llm: LLM实例

    Returns:
        更新后的AgentState
    """
    state = update_current_agent(state, AgentName.WORKFLOW)
    state = transition_to(state, NodeName.WORKFLOW)

    try:
        # TODO: 替换为真实的Workflow Agent + MCP调用
        # from tools.mcp.client import MCPClient
        # client = MCPClient(gateway_url=...)
        # result = await client.call_tool("create_case", {...})

        # Stub: 模拟创建办件
        import uuid
        stub_case_id = f"CASE_{uuid.uuid4().hex[:8].upper()}"

        mcp = MCPCallRecord(
            trace_id=state["trace_id"],
            server_name="workflow_server",
            tool_name="create_case",
            input_args={"user_id": "stub_user", "service": state.get("intent", "unknown")},
            output_result={"case_id": stub_case_id, "status": "created"},
            latency_ms=150.0,
            status=MCPCallStatus.SUCCESS,
        )
        state = record_mcp_call(state, mcp)

        # 标记workflow任务完成
        task_plan = state.get("task_plan", [])
        updated_plan: list[dict] = []
        for t in task_plan:
            agent = t.get("agent", "")
            if agent == AgentName.WORKFLOW.value and t.get("status") == TaskStatus.PENDING.value:
                t = {**t, "status": TaskStatus.COMPLETED.value}
            updated_plan.append(t)
        state["task_plan"] = updated_plan

    except Exception as e:
        logger.error(f"Workflow execution failed: {e}", exc_info=True)
        state = set_error(state, f"Workflow execution error: {e}")

    return state


# ============================================================
# Governance Node
# ============================================================


async def governance_node(
    state: AgentState,
    llm: Optional[BaseChatModel] = None,
) -> AgentState:
    """
    Governance节点 — 安全检查。

    当前为stub实现（默认通过）。
    完整实现需要接入PII检测、Prompt Injection检测、敏感词过滤。

    Args:
        state: 当前AgentState
        llm: LLM实例

    Returns:
        更新后的AgentState
    """
    state = update_current_agent(state, AgentName.GOVERNANCE)
    state = transition_to(state, NodeName.GOVERNANCE)

    try:
        # TODO: 替换为真实的Governance Agent
        # from agents.governance.security import SecurityChecker
        # from governance.guardrail import Guardrail
        # from governance.pii import PIIDesensitizer

        from orchestration.langgraph.state import GuardrailResult

        final_answer = state.get("final_answer", "")

        # Stub: 默认通过
        guard = GuardrailResult(
            passed=True,
            pii_detected=[],
            injection_detected=False,
            sensitive_words=[],
            blocked=False,
            reason=None,
        )

        state["safety_check"] = guard.model_dump()

    except Exception as e:
        logger.error(f"Governance check failed: {e}", exc_info=True)
        state = set_error(state, f"Governance check error: {e}")

    return state
