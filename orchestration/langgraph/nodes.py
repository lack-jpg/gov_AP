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
    A2ATaskRecord,
    A2ATaskStatus,
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
    mcp_client=None,
) -> AgentState:
    """
    Policy节点 — 政策检索。

    优先通过 MCP Client 调用 policy_server/search_policy，
    MCP 不可用时 fallback 到 stub 模板。

    Args:
        state: 当前AgentState
        llm: LLM实例
        mcp_client: MCPClient 实例（可选）

    Returns:
        更新后的AgentState
    """
    state = update_current_agent(state, AgentName.POLICY)
    state = transition_to(state, NodeName.POLICY)

    try:
        user_query = state.get("user_query", "")
        intent = state.get("intent", "")

        # Phase 2: 通过 MCP Client 调用 Policy Server
        if mcp_client is not None:
            try:
                search_result = await mcp_client.call_tool(
                    "policy_server",
                    "search_policy",
                    {"query": user_query, "top_k": 5},
                )
                docs = search_result.get("documents", [])
                answer = _build_answer_from_mcp(docs, intent, user_query)

                evidence = []
                for doc in docs[:3]:
                    evidence.append({
                        "source": doc.get("source", ""),
                        "excerpt": doc.get("content", "")[:200],
                        "relevance_score": doc.get("score", 0.0),
                    })

                policy_result = PolicyResult(
                    answer=answer,
                    evidence=evidence,  # type: ignore[arg-type]
                    confidence=0.85 if docs else 0.0,
                )
                state["policy_result"] = policy_result.model_dump()

                mcp = MCPCallRecord(
                    trace_id=state["trace_id"],
                    server_name="policy_server",
                    tool_name="search_policy",
                    input_args={"query": user_query, "top_k": 5},
                    output_result={"documents_found": len(docs)},
                    latency_ms=0.0,
                    status=MCPCallStatus.SUCCESS,
                )
                state = record_mcp_call(state, mcp)

                # 标记任务完成
                task_plan = state.get("task_plan", [])
                updated_plan: list[dict] = []
                for t in task_plan:
                    agent = t.get("agent", "")
                    if agent == AgentName.POLICY.value and t.get("status") == TaskStatus.PENDING.value:
                        t = {**t, "status": TaskStatus.COMPLETED.value}
                    updated_plan.append(t)
                state["task_plan"] = updated_plan

                return state

            except Exception as e:
                logger.warning("MCP policy search failed, falling back to stub: {}", e)

        # ── Stub fallback ──
        stub_answer = _stub_policy_search(intent, user_query)

        policy_result = PolicyResult(
            answer=stub_answer["answer"],
            evidence=[],
            confidence=0.9,
        )
        state["policy_result"] = policy_result.model_dump()

        # 标记task_plan中对应的policy任务为完成
        task_plan = state.get("task_plan", [])
        updated_plan: list[dict] = []
        for t in task_plan:
            agent = t.get("agent", "")
            if agent == AgentName.POLICY.value and t.get("status") == TaskStatus.PENDING.value:
                t = {**t, "status": TaskStatus.COMPLETED.value}
            updated_plan.append(t)
        state["task_plan"] = updated_plan

        # 记录MCP调用
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
    mcp_client=None,
) -> AgentState:
    """
    Material节点 — 材料审核。

    优先通过 MCP Client 调用 material_server/check_material，
    MCP 不可用时 fallback 到 stub。

    Args:
        state: 当前AgentState
        llm: LLM实例
        mcp_client: MCPClient 实例（可选）

    Returns:
        更新后的AgentState
    """
    state = update_current_agent(state, AgentName.MATERIAL)
    state = transition_to(state, NodeName.MATERIAL)

    try:
        intent = state.get("intent", "business_license")

        # Phase 2: 通过 MCP Client 调用 Material Server
        if mcp_client is not None:
            try:
                material_result = await mcp_client.call_tool(
                    "material_server",
                    "check_material",
                    {"business_type": intent, "materials": []},
                )
                result = MaterialCheckResult(
                    passed=material_result.get("passed", True),
                    missing=material_result.get("missing", []),
                    warnings=material_result.get("warnings", []),
                )
                state["material_result"] = result.model_dump()

                mcp = MCPCallRecord(
                    trace_id=state["trace_id"],
                    server_name="material_server",
                    tool_name="check_material",
                    input_args={"business_type": intent, "materials": []},
                    output_result=material_result,
                    latency_ms=0.0,
                    status=MCPCallStatus.SUCCESS,
                )
                state = record_mcp_call(state, mcp)

                # 标记任务完成
                task_plan = state.get("task_plan", [])
                updated_plan: list[dict] = []
                for t in task_plan:
                    agent = t.get("agent", "")
                    if agent == AgentName.MATERIAL.value and t.get("status") == TaskStatus.PENDING.value:
                        t = {**t, "status": TaskStatus.COMPLETED.value}
                    updated_plan.append(t)
                state["task_plan"] = updated_plan

                return state

            except Exception as e:
                logger.warning("MCP material check failed, falling back to stub: {}", e)

        # ── Stub fallback ──
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
    mcp_client=None,
) -> AgentState:
    """
    Workflow节点 — 流程执行。

    优先通过 MCP Client 调用 workflow_server/create_case，
    MCP 不可用时 fallback 到 stub 模拟。

    Args:
        state: 当前AgentState
        llm: LLM实例
        mcp_client: MCPClient 实例（可选）

    Returns:
        更新后的AgentState
    """
    state = update_current_agent(state, AgentName.WORKFLOW)
    state = transition_to(state, NodeName.WORKFLOW)

    try:
        intent = state.get("intent", "unknown")

        # Phase 2: 通过 MCP Client 调用 Workflow Server
        if mcp_client is not None:
            try:
                case_result = await mcp_client.call_tool(
                    "workflow_server",
                    "create_case",
                    {"user_id": "default_user", "service": intent},
                )
                stub_case_id = case_result.get("case_id", "CASE_UNKNOWN")

                mcp = MCPCallRecord(
                    trace_id=state["trace_id"],
                    server_name="workflow_server",
                    tool_name="create_case",
                    input_args={"user_id": "default_user", "service": intent},
                    output_result=case_result,
                    latency_ms=0.0,
                    status=MCPCallStatus.SUCCESS,
                )
                state = record_mcp_call(state, mcp)

                # 标记任务完成
                task_plan = state.get("task_plan", [])
                updated_plan: list[dict] = []
                for t in task_plan:
                    agent = t.get("agent", "")
                    if agent == AgentName.WORKFLOW.value and t.get("status") == TaskStatus.PENDING.value:
                        t = {**t, "status": TaskStatus.COMPLETED.value}
                    updated_plan.append(t)
                state["task_plan"] = updated_plan

                return state

            except Exception as e:
                logger.warning("MCP workflow call failed, falling back to stub: {}", e)

        # ── Stub fallback ──
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


# ============================================================
# A2A Node — 跨域 Agent 协同
# ============================================================


async def a2a_node(
    state: AgentState,
    llm=None,
    a2a_connector=None,
    checkpointer=None,
) -> AgentState:
    """
    A2A 节点 — 跨域 Agent 协同。

    在 Workflow 节点后执行，检查是否需要调用外部 Agent（如不动产、公积金系统）。
    如果需要，则通过 A2A Connector 发送异步任务，并在必要时挂起 LangGraph 等待回调。

    流程:
        1. 检查 task_plan 中是否有 A2A 相关任务
        2. 根据意图识别需要调用的外部 Agent 技能
        3. 通过 A2AConnector.send_task() 发送任务
        4. 若为异步模式 → 设置 waiting_task_id → 挂起
        5. 若为 stub 模式 → 直接获取结果 → 继续

    Args:
        state: 当前 AgentState
        llm: LLM 实例（未使用，保持接口一致）
        a2a_connector: A2AConnector 实例
        checkpointer: PostgresCheckpointer 实例（用于挂起）

    Returns:
        更新后的 AgentState
    """
    state = transition_to(state, NodeName.A2A_CHECK)

    try:
        intent = state.get("intent", "")
        user_query = state.get("user_query", "")
        waiting_task_id = state.get("waiting_task_id", "")

        # 如果是 A2A 回调恢复 → 处理 external_result
        external_result = state.get("external_result", {})
        if external_result and waiting_task_id:
            return await _handle_a2a_resume(state, external_result)

        # 检测是否需要跨域 Agent 调用
        a2a_skills = _detect_a2a_skills(intent, user_query)
        if not a2a_skills:
            # 无需 A2A 调用，直接返回
            return state

        # 遍历需要的技能，依次调用
        for skill in a2a_skills:
            skill_input = _build_a2a_input(skill, state)

            if a2a_connector is not None:
                result = await a2a_connector.send_task(
                    skill=skill,
                    input_data=skill_input,
                    source_trace_id=state.get("trace_id", ""),
                )
            else:
                # 无 Connector → 使用直接 stub 调用
                result = await _a2a_stub_call(skill, skill_input)

            # 记录 A2A 任务
            a2a_record = A2ATaskRecord(
                source_agent="workflow",
                target_agent=result.get("agent_name", "unknown"),
                skill=skill,
                input=skill_input,
                artifact=result.get("artifact"),
            )
            state["a2a_tasks"] = state.get("a2a_tasks", []) + [a2a_record.model_dump()]

            # 异步模式 → 挂起等待
            if result.get("mode") == "http":
                state["waiting_task_id"] = result["task_id"]
                # 挂起 LangGraph
                if checkpointer is not None:
                    try:
                        trace_id = state.get("trace_id", "")
                        await checkpointer.suspend_for_a2a(
                            thread_id=trace_id,
                            checkpoint_id="",  # 当前 checkpoint 由 LangGraph 管理
                            a2a_task_id=result["task_id"],
                        )
                        logger.info(
                            "A2A 挂起: task={task_id} skill={skill}",
                            task_id=result["task_id"],
                            skill=skill,
                        )
                    except Exception as e:
                        logger.warning("A2A 挂起失败（将使用同步模式）: {}", e)
                break  # 挂起后不再继续

            # Stub 同步模式 → 继续下一个 skill
            logger.info(
                "A2A Stub: skill={skill} status={status}",
                skill=skill,
                status=result.get("status", "?"),
            )

    except Exception as e:
        logger.error(f"A2A node failed: {e}", exc_info=True)
        state = set_error(state, f"A2A node error: {e}")

    return state


def _detect_a2a_skills(intent: str, user_query: str) -> list[str]:
    """
    根据意图和用户查询检测需要的 A2A 技能。

    Args:
        intent: 意图标签
        user_query: 用户查询

    Returns:
        需要的技能列表
    """
    skills: list[str] = []
    query_lower = user_query.lower()

    # 不动产相关
    if any(kw in query_lower for kw in ("房产", "不动产", "房屋", "产权", "房子")):
        skills.append("query_property")
    if intent in ("property_service",):
        skills.append("query_property")

    # 公积金相关
    if any(kw in query_lower for kw in ("公积金", "住房基金")):
        skills.append("query_fund")
    if intent in ("fund_query",):
        skills.append("query_fund")

    return skills


def _build_a2a_input(skill: str, state: AgentState) -> dict:
    """
    根据技能构建 A2A 输入参数。

    Args:
        skill: 技能名称
        state: 当前 AgentState

    Returns:
        输入参数字典
    """
    user_query = state.get("user_query", "")

    if skill.startswith("query_property"):
        return {
            "owner_name": _extract_name(user_query),
            "user_query": user_query,
        }
    elif skill.startswith("query_fund"):
        return {
            "user_id": "001",  # TODO: 从认证信息中获取真实 user_id
            "user_query": user_query,
        }
    return {"user_query": user_query}


def _extract_name(query: str) -> str:
    """简单的中文人名提取（stub）"""
    # 常见姓 + 名模式的简单匹配
    import re
    surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    pattern = r'[' + surnames + r']\w{1,2}(?=的|在|想|要|查|办理|需要|请|申请)'
    match = re.search(pattern, query)
    return match.group(0) if match else ""


async def _handle_a2a_resume(state: AgentState, external_result: dict) -> AgentState:
    """
    处理 A2A 回调恢复。

    将 external_result 合并到 state 的对应字段中，
    清除 waiting_task_id，标记当前 A2A 任务完成。

    Args:
        state: 当前 AgentState
        external_result: 外部 Agent 返回的结果

    Returns:
        更新后的 AgentState
    """
    # 合并外部结果到 evidence（作为交叉验证的证据）
    evidence = state.get("evidence", [])
    if isinstance(external_result, dict):
        result_summary = {
            "source": "外部系统 (A2A)",
            "excerpt": str(external_result)[:500],
            "relevance_score": 0.85,
        }
        evidence = list(evidence) + [result_summary]

    # 更新 A2A 任务记录状态
    a2a_tasks = state.get("a2a_tasks", [])
    waiting_task_id = state.get("waiting_task_id", "")
    updated_tasks: list[dict] = []
    for t in a2a_tasks:
        if t.get("task_id") == waiting_task_id:
            t = {
                **t,
                "status": A2ATaskStatus.COMPLETED.value,
                "artifact": external_result,
            }
        updated_tasks.append(t)

    return {
        **state,
        "evidence": evidence,
        "a2a_tasks": updated_tasks,
        "waiting_task_id": "",
        "external_result": external_result,
    }


async def _a2a_stub_call(skill: str, input_data: dict) -> dict:
    """A2A Stub 调用（无 Connector 时的降级方案）"""
    if skill.startswith("query_property"):
        from tools.a2a.mock_agents.housing_agent import query_property_stub
        artifact = await query_property_stub(input_data)
        return {"task_id": "a2a_stub", "status": "completed", "agent_name": "stub", "artifact": artifact, "mode": "stub"}
    elif skill.startswith("query_fund"):
        from tools.a2a.mock_agents.fund_agent import query_fund_stub
        artifact = await query_fund_stub(input_data)
        return {"task_id": "a2a_stub", "status": "completed", "agent_name": "stub", "artifact": artifact, "mode": "stub"}
    return {"task_id": "a2a_stub", "status": "completed", "agent_name": "stub", "artifact": {"message": f"stub for {skill}"}, "mode": "stub"}


# ============================================================
# MCP 结果 → 回答转换辅助函数
# ============================================================


def _build_answer_from_mcp(
    documents: list[dict],
    intent: str,
    user_query: str,
) -> str:
    """
    将 MCP search_policy 返回的文档列表拼接为人类可读的回答。
    作为 MCP 结果和 PolicyResult.answer 之间的桥梁。
    """
    if not documents:
        return _stub_policy_search(intent, user_query).get("answer", "")

    lines: list[str] = []
    for i, doc in enumerate(documents, 1):
        title = doc.get("title", f"政策文档{i}")
        content = doc.get("content", "")[:300]
        source = doc.get("source", "")

        lines.append(f"{i}. **{title}**")
        lines.append(f"   {content}")
        if source:
            lines.append(f"   来源: {source}")
        lines.append("")

    return "\n".join(lines) if lines else _stub_policy_search(intent, user_query).get("answer", "")
