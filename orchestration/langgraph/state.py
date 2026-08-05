"""
langgraph.state - AgentState definition: shared state across all LangGraph nodes

Author: le
Date: 2026/7/29
Version: 0.1
Task: Define TypedDict AgentState with trace_id, user_query, intent, task_plan, messages, etc.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from operator import add
from typing import Annotated, Any, Optional, TypedDict

from pydantic import BaseModel, Field


# ============================================================
# Enums
# ============================================================


class RiskLevel(str, Enum):
    """风险等级"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    """子任务执行状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MCPCallStatus(str, Enum):
    """MCP工具调用状态"""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"          # 被Gateway/RBAC拦截


class A2ATaskStatus(str, Enum):
    """A2A跨域任务状态"""

    CREATED = "created"
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class AgentName(str, Enum):
    """Agent名称常量"""

    SUPERVISOR = "supervisor"
    INTENT = "intent"
    POLICY = "policy"
    MATERIAL = "material"
    WORKFLOW = "workflow"
    GOVERNANCE = "governance"


class NodeName(str, Enum):
    """LangGraph节点名称"""

    SUPERVISOR = "supervisor_node"
    INTENT = "intent_node"
    POLICY = "policy_node"
    MATERIAL = "material_node"
    WORKFLOW = "workflow_node"
    GOVERNANCE = "governance_node"
    PLANNER = "planner_node"
    A2A_CHECK = "a2a_node"


# ============================================================
# Pydantic Models — 子结构（强类型，序列化友好）
# ============================================================


class Task(BaseModel):
    """Supervisor拆解出的子任务"""

    id: str = Field(
        default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}",
        description="子任务唯一标识，自动生成 (task_xxxxxxxx)",
    )
    type: str = Field(
        description="任务类型: search_policy | check_material | create_case | query_status | ..."
    )
    agent: AgentName = Field(
        description="负责执行该子任务的Agent名称 (supervisor | intent | policy | material | workflow)"
    )
    description: str = Field(
        default="",
        description="子任务的人类可读描述，便于trace和debug时理解任务内容",
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="子任务的输入参数，传递给目标Agent的具体数据",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="依赖的前置任务ID列表，只有依赖任务全部COMPLETED后本任务才能开始执行",
    )
    priority: int = Field(
        default=0,
        description="任务优先级，数字越大越优先执行，默认为0",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="任务当前状态: pending | running | completed | failed | skipped",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="任务创建时间 (ISO 8601 UTC格式)",
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="任务完成时间 (ISO 8601 UTC格式)，未完成时为None",
    )


class Evidence(BaseModel):
    """政策证据引用（Policy Agent必须返回，保证回答可追溯、可审核）"""

    source: str = Field(
        description="来源文件名或法规名称，如 '食品经营许可条例'、'城市管理法第X条'",
    )
    excerpt: str = Field(
        description="引用的政策原文片段，用于支撑回答的可靠性",
    )
    page: Optional[int] = Field(
        default=None,
        description="政策文件中的页码，方便人工复核时定位",
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="该证据与查询的相关性分数，0.0~1.0，由Reranker输出",
    )


class PolicyResult(BaseModel):
    """Policy Agent检索结果"""

    answer: str = Field(description="基于政策的回答")
    evidence: list[Evidence] = Field(default_factory=list, description="证据引用列表")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="回答置信度")


class IntentResult(BaseModel):
    """Intent Agent意图识别结果"""

    label: str = Field(
        description="意图标签ID: business_license | business_register | fund_query | property_service | restaurant_license | ..."
    )
    label_name: str = Field(
        default="",
        description="意图标签的中文名称，如 '营业执照办理'、'公积金查询'",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="分类置信度，0.0~1.0。低于阈值时触发LLM fallback",
    )
    source: str = Field(
        default="bert",
        description="识别来源: bert (BERT模型分类) | llm (大模型fallback)",
    )


class MaterialCheckResult(BaseModel):
    """Material Agent材料审核结果"""

    passed: bool = Field(
        default=False,
        description="材料审核是否通过，True表示所有必需材料已提交且格式正确",
    )
    missing: list[str] = Field(
        default_factory=list,
        description="缺失的材料名称列表，如 ['营业场所证明', '食品经营许可证']",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="审核警告信息列表，材料虽全但有瑕疵时产生，如 '身份证照片模糊'",
    )
    extracted_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="从材料中抽取到的结构化字段，如 {name: '张三', id_card: '110***********1234'}",
    )


class MCPCallRecord(BaseModel):
    """单次MCP工具调用记录（所有MCP调用必须记录，用于审计和评测）"""

    trace_id: str = Field(
        description="关联的链路追踪ID，与AgentState.trace_id一致",
    )
    server_name: str = Field(
        description="目标MCP Server名称: policy_server | material_server | workflow_server",
    )
    tool_name: str = Field(
        description="调用的工具名: search_policy | get_policy_detail | extract_entity | check_material | create_case | query_status",
    )
    input_args: dict[str, Any] = Field(
        default_factory=dict,
        description="工具调用的输入参数，如 {query: '开餐馆需要什么', top_k: 5}",
    )
    output_result: Optional[dict[str, Any]] = Field(
        default=None,
        description="工具调用的返回结果，调用失败时为None",
    )
    latency_ms: float = Field(
        default=0.0,
        description="工具调用耗时，单位毫秒（ms）",
    )
    status: MCPCallStatus = Field(
        default=MCPCallStatus.SUCCESS,
        description="调用状态: success | failed | timeout | blocked(被Gateway/RBAC拦截)",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="调用失败时的错误信息，成功时为None",
    )
    called_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="工具调用发起时间 (ISO 8601 UTC格式)",
    )


class ToolCall(BaseModel):
    """Agent端的单次工具调用记录（LangGraph内tool_calls追踪）"""

    tool_name: str = Field(
        description="被调用的工具名称，如 search_policy、create_case",
    )
    tool_call_id: str = Field(
        default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}",
        description="工具调用的唯一标识，自动生成 (call_xxxxxxxx)，用于去重和关联",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="工具调用的实际参数，LLM填写的键值对",
    )
    result: Optional[str] = Field(
        default=None,
        description="工具调用的返回结果字符串，调用失败时为None",
    )
    error: Optional[str] = Field(
        default=None,
        description="工具调用失败时的错误信息字符串，成功时为None",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="工具调用发生时间 (ISO 8601 UTC格式)",
    )


class A2ATaskRecord(BaseModel):
    """A2A跨域任务记录（一次完整的跨系统Agent调用）"""

    task_id: str = Field(
        default_factory=lambda: f"a2a_{uuid.uuid4().hex[:8]}",
        description="A2A任务唯一标识，自动生成 (a2a_xxxxxxxx)，用于Callback关联",
    )
    source_agent: str = Field(
        description="发起任务的本系统Agent名称，如 supervisor | workflow",
    )
    target_agent: str = Field(
        description="目标外部Agent名称: housing_agent (不动产) | fund_agent (公积金) | ...",
    )
    skill: str = Field(
        description="调用的外部Agent技能: query_property | query_fund | query_medical | ...",
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="发送给外部Agent的请求参数，只包含必要字段（数据最小化原则）",
    )
    artifact: Optional[dict[str, Any]] = Field(
        default=None,
        description="外部Agent返回的结果数据（artifact），任务完成前为None",
    )
    status: A2ATaskStatus = Field(
        default=A2ATaskStatus.CREATED,
        description="任务生命周期状态: created | submitted | working | completed | failed | timeout",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="任务创建时间 (ISO 8601 UTC格式)",
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="任务完成时间 (ISO 8601 UTC格式)，未完成时为None",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="任务失败或超时时的错误信息，正常完成时为None",
    )


class ExecutionMetrics(BaseModel):
    """单次Agent执行的性能指标（用于Trace持久化和Evaluation评测）"""

    trace_id: str = Field(
        description="关联的链路追踪ID，与AgentState.trace_id一致",
    )
    agent_name: str = Field(
        description="被统计的Agent名称 (supervisor | intent | policy | material | workflow | governance)",
    )
    input_tokens: int = Field(
        default=0,
        description="LLM输入Token数量",
    )
    output_tokens: int = Field(
        default=0,
        description="LLM输出Token数量",
    )
    latency_ms: float = Field(
        default=0.0,
        description="Agent执行总耗时，单位毫秒（ms）",
    )
    tool_calls_count: int = Field(
        default=0,
        description="该Agent发起的MCP工具调用总次数",
    )
    tool_errors_count: int = Field(
        default=0,
        description="该Agent发起的MCP工具调用失败次数，用于计算Tool Accuracy",
    )
    step_count: int = Field(
        default=0,
        description="Agent执行的步骤数（LangGraph节点跳转次数），用于检测是否存在不必要的循环",
    )
    success: bool = Field(
        default=True,
        description="本次Agent执行是否成功完成",
    )


class GuardrailResult(BaseModel):
    """安全护栏检测结果（Governance Agent输入/输出安全检查）"""

    passed: bool = Field(
        default=True,
        description="安全检查是否通过，True表示未检测到任何安全问题",
    )
    pii_detected: list[str] = Field(
        default_factory=list,
        description="检测到的PII类型列表: ['phone', 'id_card', 'email']",
    )
    injection_detected: bool = Field(
        default=False,
        description="是否检测到Prompt Injection攻击尝试",
    )
    sensitive_words: list[str] = Field(
        default_factory=list,
        description="检测到的敏感词列表（政务场景特定敏感词库）",
    )
    blocked: bool = Field(
        default=False,
        description="是否拦截本次请求，True时不应继续执行",
    )
    reason: Optional[str] = Field(
        default=None,
        description="拦截原因说明，如 '检测到身份证号未脱敏'，未拦截时为None",
    )


# ============================================================
# Reducer Functions — 用于 LangGraph Annotated State 的累加逻辑
# ============================================================


def _task_plan_reducer(current: list[dict], update: list[dict]) -> list[dict]:
    """Task plan reducer: 合并更新，按ID去重，相同ID用新的覆盖"""
    merged = {t["id"] if isinstance(t, dict) else t.id: t for t in current}
    for item in update:
        key = item["id"] if isinstance(item, dict) else item.id
        merged[key] = item
    return list(merged.values())


def _append_reducer(current: list, update: list) -> list:
    """追加模式的reducer: 新元素追加到现有列表末尾"""
    return (current or []) + (update or [])


def _tool_calls_reducer(current: list[dict], update: list[dict]) -> list[dict]:
    """Tool calls reducer: 按 tool_call_id 去重合并"""
    merged = {tc["tool_call_id"] if isinstance(tc, dict) else tc.tool_call_id: tc for tc in (current or [])}
    for item in (update or []):
        key = item["tool_call_id"] if isinstance(item, dict) else item.tool_call_id
        merged[key] = item
    return list(merged.values())


# ============================================================
# AgentState — LangGraph 共享状态
# ============================================================


class AgentState(TypedDict):
    """
    LangGraph Agent共享状态。

    字段按更新策略分为两类：

    **覆盖更新（标量/单值）** — 每次节点返回新值直接替换：
        trace_id, user_query, intent, current_agent, final_answer, risk_level,
        safety_check, execution_metrics

    **追加更新（列表）** — 使用 Annotated + reducer 实现累加：
        task_plan: merge by id
        messages: LangGraph内置 add_messages
        tool_calls: merge by tool_call_id
        mcp_history: append only
        a2a_tasks: merge by task_id
        evidence: append only
    """

    # ── 请求标识 ──
    trace_id: str
    """全链路追踪ID，在API Gateway层生成，贯穿所有Agent和MCP调用"""

    # ── 用户输入 ──
    user_query: str
    """用户原始自然语言输入"""

    # ── Intent ──
    intent: str
    """Intent Agent识别出的意图标签，如 business_license / fund_query"""

    intent_result: dict
    """Intent Agent完整识别结果（包含置信度、来源等），IntentResult的字典形式"""

    # ── 任务规划 ──
    task_plan: Annotated[list[dict], _task_plan_reducer]
    """Supervisor拆解的子任务列表，每个元素为Task模型的字典"""

    # ── 当前执行 ──
    current_agent: str
    """当前正在执行的Agent名称（AgentName枚举值）"""

    current_node: str
    """当前所在LangGraph节点名称（NodeName枚举值）"""

    # ── 对话 ──
    messages: Annotated[list[dict], add]
    """对话消息历史（兼容LangChain message格式）。
    使用 operator.add 作为reducer，新消息追加到列表末尾"""

    # ── 工具调用 ──
    tool_calls: Annotated[list[dict], _tool_calls_reducer]
    """Agent端的工具调用记录列表，每个元素为ToolCall模型的字典"""

    # ── MCP调用历史 ──
    mcp_history: Annotated[list[dict], _append_reducer]
    """MCP Client调用记录列表，每个元素为MCPCallRecord模型的字典。
    所有MCP调用必须记录于此，用于审计和评测"""

    # ── A2A跨域任务 ──
    a2a_tasks: Annotated[list[dict], _append_reducer]
    """A2A跨域任务列表，每个元素为A2ATaskRecord模型的字典"""

    # ── 外部队列 ──
    waiting_task_id: str
    """当前等待中的A2A任务ID，非空时表示LangGraph已interrupt挂起"""

    external_result: dict
    """A2A Callback恢复后注入的外部Agent返回结果"""

    # ── 知识证据 ──
    evidence: Annotated[list[dict], _append_reducer]
    """Policy Agent检索到的政策证据列表，每个元素为Evidence模型的字典"""

    policy_result: dict
    """Policy Agent完整检索结果（PolicyResult模型的字典）"""

    # ── 材料审核 ──
    material_result: dict
    """Material Agent审核结果（MaterialCheckResult模型的字典）"""

    # ── 最终输出 ──
    final_answer: str
    """最终返回给用户的答案"""

    # ── 安全 ──
    risk_level: str
    """Governance Agent评估的风险等级: low | medium | high | critical"""

    safety_check: dict
    """GuardrailResult模型的字典，安全护栏检测结果"""

    # ── 执行指标 ──
    execution_metrics: dict
    """ExecutionMetrics模型的字典，单次执行的指标汇总"""

    # ── 错误处理 ──
    error: str
    """当前错误信息，非空表示执行中遇到了错误"""

    error_history: Annotated[list[dict], _append_reducer]
    """历史错误记录列表"""

    retry_count: int
    """当前重试次数"""


# ============================================================
# Factory — 创建初始State
# ============================================================


def create_initial_state(
    user_query: str,
    trace_id: Optional[str] = None,
) -> AgentState:
    """
    创建初始AgentState。

    所有列表字段初始化为空列表，标量字段设置默认值。
    在API Gateway收到用户请求后调用。

    Args:
        user_query: 用户原始输入
        trace_id: 链路追踪ID，不传则自动生成

    Returns:
        初始化后的AgentState
    """
    if trace_id is None:
        trace_id = f"trace_{uuid.uuid4().hex[:16]}"

    return AgentState(
        # 请求标识
        trace_id=trace_id,
        # 用户输入
        user_query=user_query,
        # Intent
        intent="",
        intent_result={},
        # 任务规划
        task_plan=[],
        # 当前执行
        current_agent=AgentName.SUPERVISOR.value,
        current_node="",
        # 对话
        messages=[],
        # 工具调用
        tool_calls=[],
        # MCP调用历史
        mcp_history=[],
        # A2A跨域任务
        a2a_tasks=[],
        # 外部队列
        waiting_task_id="",
        external_result={},
        # 知识证据
        evidence=[],
        policy_result={},
        # 材料审核
        material_result={},
        # 最终输出
        final_answer="",
        # 安全
        risk_level=RiskLevel.LOW.value,
        safety_check={},
        # 执行指标
        execution_metrics={},
        # 错误处理
        error="",
        error_history=[],
        retry_count=0,
    )


# ============================================================
# Helper — State操作工具函数
# ============================================================


def update_current_agent(state: AgentState, agent: AgentName) -> AgentState:
    """设置当前执行的Agent"""
    return {**state, "current_agent": agent.value}


def set_intent(state: AgentState, result: IntentResult) -> AgentState:
    """设置意图识别结果"""
    return {
        **state,
        "intent": result.label,
        "intent_result": result.model_dump(),
    }


def add_task(state: AgentState, task: Task) -> AgentState:
    """向task_plan追加一个子任务（调用内部reducer确保合并而非覆盖）"""
    task_dict = task.model_dump()
    current: list[dict] = state.get("task_plan", [])  # type: ignore[assignment]
    return {
        **state,
        "task_plan": _task_plan_reducer(current, [task_dict]),
    }


def add_evidence(state: AgentState, evidence_list: list[Evidence]) -> AgentState:
    """追加政策证据（调用内部reducer确保合并而非覆盖）"""
    ev_dicts = [e.model_dump() for e in evidence_list]
    current: list[dict] = state.get("evidence", [])  # type: ignore[assignment]
    return {
        **state,
        "evidence": _append_reducer(current, ev_dicts),
    }


def record_mcp_call(state: AgentState, record: MCPCallRecord) -> AgentState:
    """记录一次MCP调用（调用内部reducer确保合并而非覆盖）"""
    record_dict = record.model_dump()
    current: list[dict] = state.get("mcp_history", [])  # type: ignore[assignment]
    return {
        **state,
        "mcp_history": _append_reducer(current, [record_dict]),
    }


def set_error(state: AgentState, error_message: str) -> AgentState:
    """设置当前错误，并将错误追加到error_history（调用内部reducer确保合并）"""
    error_entry = {
        "message": error_message,
        "agent": state.get("current_agent", ""),
        "node": state.get("current_node", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    current_history: list[dict] = state.get("error_history", [])  # type: ignore[assignment]
    return {
        **state,
        "error": error_message,
        "error_history": _append_reducer(current_history, [error_entry]),
    }


def clear_error(state: AgentState) -> AgentState:
    """清除当前错误并增加重试计数"""
    return {
        **state,
        "error": "",
        "retry_count": state.get("retry_count", 0) + 1,
    }


def set_final_answer(state: AgentState, answer: str) -> AgentState:
    """设置最终答案"""
    return {**state, "final_answer": answer}


def transition_to(state: AgentState, node: NodeName) -> AgentState:
    """标记即将进入的LangGraph节点"""
    return {**state, "current_node": node.value}


# ============================================================
# Type Aliases — 便捷类型引用
# ============================================================

# State更新函数签名: 接受当前state，返回更新后的部分state字典
StateUpdate = dict[str, Any]

# LangGraph节点函数签名
NodeFunction = Any  # Callable[[AgentState], AgentState] — 实际类型由LangGraph推断

# Router函数签名: 根据当前state返回下一个节点名
RouterFunction = Any  # Callable[[AgentState], str]


# ============================================================
# Smoke Test — python -m orchestration.langgraph.state
# ============================================================

if __name__ == "__main__":
    import json
    import traceback
    from typing import get_type_hints

    passed = 0
    failed = 0

    def check(description: str, condition: bool, detail: str = ""):
        """断言并计数"""
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {description}")
        else:
            failed += 1
            print(f"  [FAIL] {description}")
            if detail:
                print(f"         {detail}")

    def section(title: str):
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")

    # ────────────────────────────────────────────────
    # 1. Enums
    # ────────────────────────────────────────────────
    section("1. Enums")

    check("RiskLevel has 4 members", len(RiskLevel) == 4)
    check("RiskLevel.LOW == 'low'", RiskLevel.LOW.value == "low")
    check("RiskLevel.CRITICAL == 'critical'", RiskLevel.CRITICAL.value == "critical")

    check("TaskStatus has 5 members", len(TaskStatus) == 5)
    check("TaskStatus.PENDING is first state", TaskStatus.PENDING.value == "pending")

    check("MCPCallStatus has 4 members", len(MCPCallStatus) == 4)
    check("MCPCallStatus.BLOCKED exists", MCPCallStatus.BLOCKED.value == "blocked")

    check("A2ATaskStatus has 6 members", len(A2ATaskStatus) == 6)
    check("A2ATaskStatus lifecycle order",
          list(A2ATaskStatus)[:3] == [A2ATaskStatus.CREATED, A2ATaskStatus.SUBMITTED, A2ATaskStatus.WORKING])

    check("AgentName has 6 members", len(AgentName) == 6)
    check("AgentName.SUPERVISOR == 'supervisor'", AgentName.SUPERVISOR.value == "supervisor")

    check("NodeName has 8 members", len(NodeName) == 8)
    check("NodeName.SUPERVISOR == 'supervisor_node'", NodeName.SUPERVISOR.value == "supervisor_node")

    # ────────────────────────────────────────────────
    # 2. Pydantic Models — 基本实例化
    # ────────────────────────────────────────────────
    section("2. Pydantic Models — 实例化")

    # Task
    task = Task(type="search_policy", agent=AgentName.POLICY, description="查询餐饮许可政策")
    check("Task.id auto-generated", task.id.startswith("task_"))
    check("Task.type == 'search_policy'", task.type == "search_policy")
    check("Task.status default == PENDING", task.status == TaskStatus.PENDING)
    check("Task.created_at is ISO 8601", "T" in task.created_at and task.completed_at is None)

    task2 = Task(type="check_material", agent=AgentName.MATERIAL, priority=5,
                 dependencies=[task.id])
    check("Task.dependencies linked correctly", task2.dependencies == [task.id])

    # Evidence
    evidence = Evidence(source="食品经营许可条例", excerpt="第十条：申请食品经营许可，应当提交...", page=10, relevance_score=0.92)
    check("Evidence.source", evidence.source == "食品经营许可条例")
    check("Evidence.relevance_score in [0,1]", 0.0 <= evidence.relevance_score <= 1.0)

    # PolicyResult
    pr = PolicyResult(answer="需要营业执照和食品经营许可证", evidence=[evidence], confidence=0.89)
    check("PolicyResult.answer", "营业执照" in pr.answer)
    check("PolicyResult.evidence count == 1", len(pr.evidence) == 1)

    # IntentResult
    ir = IntentResult(label="business_license", label_name="营业执照办理", confidence=0.95, source="bert")
    check("IntentResult.label", ir.label == "business_license")
    check("IntentResult.source == 'bert'", ir.source == "bert")

    # MaterialCheckResult
    mr = MaterialCheckResult(passed=False, missing=["营业场所证明"], warnings=["身份证照片模糊"])
    check("MaterialCheckResult.passed == False", mr.passed is False)
    check("MaterialCheckResult.missing[0]", mr.missing[0] == "营业场所证明")

    # MCPCallRecord
    mcp = MCPCallRecord(
        trace_id="trace_abc123",
        server_name="policy_server",
        tool_name="search_policy",
        input_args={"query": "开餐馆需要什么", "top_k": 5},
        latency_ms=234.5,
    )
    check("MCPCallRecord.tool_name", mcp.tool_name == "search_policy")
    check("MCPCallRecord.status default == SUCCESS", mcp.status == MCPCallStatus.SUCCESS)
    check("MCPCallRecord.error_message is None", mcp.error_message is None)

    mcp_fail = MCPCallRecord(
        trace_id="trace_fail", server_name="material_server", tool_name="check_material",
        status=MCPCallStatus.FAILED, error_message="OCR service unavailable",
    )
    check("MCPCallRecord failed status", mcp_fail.status == MCPCallStatus.FAILED)

    # ToolCall
    tc = ToolCall(tool_name="search_policy", arguments={"query": "test"},
                  result="找到3条相关法规", timestamp="2026-07-29T10:00:00Z")
    check("ToolCall.tool_call_id auto-generated", tc.tool_call_id.startswith("call_"))
    check("ToolCall.result is not None", tc.result is not None)

    # A2ATaskRecord
    a2a = A2ATaskRecord(
        source_agent="supervisor", target_agent="housing_agent",
        skill="query_property", input={"user_id": "001"},
    )
    check("A2ATaskRecord.task_id starts with a2a_", a2a.task_id.startswith("a2a_"))
    check("A2ATaskRecord.status default == CREATED", a2a.status == A2ATaskStatus.CREATED)
    check("A2ATaskRecord.artifact is None", a2a.artifact is None)

    # ExecutionMetrics
    metrics = ExecutionMetrics(trace_id="trace_abc", agent_name="policy_agent",
                               input_tokens=150, output_tokens=300, latency_ms=520.0,
                               tool_calls_count=2, step_count=3)
    check("ExecutionMetrics.input_tokens", metrics.input_tokens == 150)
    check("ExecutionMetrics.success default == True", metrics.success is True)

    # GuardrailResult
    guard_ok = GuardrailResult()
    check("GuardrailResult default passed == True", guard_ok.passed is True)
    check("GuardrailResult default blocked == False", guard_ok.blocked is False)

    guard_block = GuardrailResult(
        passed=False, pii_detected=["phone", "id_card"], injection_detected=False,
        blocked=True, reason="检测到未脱敏的个人敏感信息",
    )
    check("GuardrailResult blocked", guard_block.blocked is True)
    check("GuardrailResult.reason", guard_block.reason is not None)

    # ────────────────────────────────────────────────
    # 3. Pydantic Models — 序列化/反序列化
    # ────────────────────────────────────────────────
    section("3. Pydantic Models — model_dump / model_validate")

    # 序列化
    task_dict = task.model_dump()
    check("Task.model_dump() produces dict", isinstance(task_dict, dict))
    check("Task dict has all keys", set(task_dict.keys()) >= {"id", "type", "agent", "description", "status"})

    # JSON 序列化
    task_json = task.model_dump_json()
    check("Task.model_dump_json() produces valid JSON", isinstance(task_json, str))
    parsed = json.loads(task_json)
    check("Task JSON parses back", parsed["type"] == "search_policy")

    # 反序列化
    task_roundtrip = Task.model_validate(task_dict)
    check("Task round-trip: type matches", task_roundtrip.type == task.type)
    check("Task round-trip: status matches", task_roundtrip.status == task.status)

    # Evidence 序列化
    ev_dict = evidence.model_dump()
    check("Evidence.model_dump() round-trip", Evidence.model_validate(ev_dict).source == evidence.source)

    # A2ATaskRecord 序列化（含Optional字段）
    a2a_dict = a2a.model_dump()
    check("A2ATaskRecord JSON serializable", json.dumps(a2a_dict) is not None)

    # MCPCallRecord with Optional None
    mcp_dict = mcp.model_dump()
    check("MCPCallRecord.error_message is None in dict", mcp_dict["error_message"] is None)

    # ────────────────────────────────────────────────
    # 4. Pydantic Models — 字段约束校验
    # ────────────────────────────────────────────────
    section("4. Pydantic Models — 字段约束")

    # Evidence.relevance_score 边界
    try:
        Evidence(source="test", excerpt="test", relevance_score=1.5)
        check("Evidence.relevance_score > 1.0 should be rejected", False, "Expected ValidationError")
    except Exception:
        check("Evidence.relevance_score <= 1.0 constraint works", True)

    try:
        Evidence(source="test", excerpt="test", relevance_score=-0.1)
        check("Evidence.relevance_score < 0.0 should be rejected", False, "Expected ValidationError")
    except Exception:
        check("Evidence.relevance_score >= 0.0 constraint works", True)

    # IntentResult.confidence 边界
    try:
        IntentResult(label="test", confidence=2.0)
        check("IntentResult.confidence > 1.0 should be rejected", False, "Expected ValidationError")
    except Exception:
        check("IntentResult.confidence <= 1.0 constraint works", True)

    # MCPCallRecord 必填字段
    try:
        MCPCallRecord()
        check("MCPCallRecord missing trace_id should be rejected", False, "Expected ValidationError")
    except Exception:
        check("MCPCallRecord.trace_id is required", True)

    # ────────────────────────────────────────────────
    # 5. create_initial_state()
    # ────────────────────────────────────────────────
    section("5. create_initial_state()")

    state = create_initial_state(user_query="我要开一家餐馆")
    check("Return type is dict", isinstance(state, dict))
    check("trace_id starts with trace_", state["trace_id"].startswith("trace_"))
    check("user_query preserved", state["user_query"] == "我要开一家餐馆")
    check("intent is empty string", state["intent"] == "")
    check("task_plan is empty list", state["task_plan"] == [])
    check("current_agent == 'supervisor'", state["current_agent"] == "supervisor")
    check("current_node is empty string", state["current_node"] == "")
    check("messages is empty list", state["messages"] == [])
    check("tool_calls is empty list", state["tool_calls"] == [])
    check("mcp_history is empty list", state["mcp_history"] == [])
    check("a2a_tasks is empty list", state["a2a_tasks"] == [])
    check("waiting_task_id is empty string", state["waiting_task_id"] == "")
    check("external_result is empty dict", state["external_result"] == {})
    check("evidence is empty list", state["evidence"] == [])
    check("policy_result is empty dict", state["policy_result"] == {})
    check("material_result is empty dict", state["material_result"] == {})
    check("final_answer is empty string", state["final_answer"] == "")
    check("risk_level == 'low'", state["risk_level"] == "low")
    check("safety_check is empty dict", state["safety_check"] == {})
    check("execution_metrics is empty dict", state["execution_metrics"] == {})
    check("error is empty string", state["error"] == "")
    check("error_history is empty list", state["error_history"] == [])
    check("retry_count == 0", state["retry_count"] == 0)

    # 自定义 trace_id
    state_custom = create_initial_state(user_query="test", trace_id="my_trace_001")
    check("custom trace_id preserved", state_custom["trace_id"] == "my_trace_001")

    # ────────────────────────────────────────────────
    # 6. Reducer Functions
    # ────────────────────────────────────────────────
    section("6. Reducer Functions")

    # _task_plan_reducer: merge by id
    t1 = Task(type="search_policy", agent=AgentName.POLICY).model_dump()
    t2 = Task(type="check_material", agent=AgentName.MATERIAL).model_dump()
    merged = _task_plan_reducer([t1], [t2])
    check("task_plan_reducer appends new task", len(merged) == 2)
    # 更新已存在的task
    t1_updated = {**t1, "status": TaskStatus.COMPLETED.value}
    merged2 = _task_plan_reducer([t1], [t1_updated])
    check("task_plan_reducer updates by id", merged2[0]["status"] == "completed")

    # _tool_calls_reducer: merge by tool_call_id
    c1 = ToolCall(tool_name="search_policy").model_dump()
    c2 = ToolCall(tool_name="check_material").model_dump()
    merged_tc = _tool_calls_reducer([c1], [c2])
    check("tool_calls_reducer appends new call", len(merged_tc) == 2)
    # 更新已存在的
    c1_updated = {**c1, "result": "found 5 docs"}
    merged_tc2 = _tool_calls_reducer([c1], [c1_updated])
    check("tool_calls_reducer updates by tool_call_id", merged_tc2[0]["result"] == "found 5 docs")

    # _append_reducer: simple append
    r1 = _append_reducer(None, [1, 2])
    check("_append_reducer handles None current", r1 == [1, 2])
    r2 = _append_reducer([1, 2], [3, 4])
    check("_append_reducer appends correctly", r2 == [1, 2, 3, 4])
    r3 = _append_reducer([1], [])
    check("_append_reducer handles empty update", r3 == [1])

    # ────────────────────────────────────────────────
    # 7. Helper Functions — State 操作
    # ────────────────────────────────────────────────
    section("7. Helper Functions")

    # set_intent
    intent_result = IntentResult(label="restaurant_license", label_name="餐饮许可",
                                 confidence=0.93, source="bert")
    state2 = set_intent(state, intent_result)
    check("set_intent: intent label", state2["intent"] == "restaurant_license")
    check("set_intent: intent_result dict", state2["intent_result"]["confidence"] == 0.93)

    # add_task
    new_task = Task(type="search_policy", agent=AgentName.POLICY, description="查询政策")
    state3 = add_task(state2, new_task)
    check("add_task: task added", len(state3["task_plan"]) == 1)
    check("add_task: task type", state3["task_plan"][0]["type"] == "search_policy")

    # add_evidence
    ev_list = [
        Evidence(source="条例A", excerpt="规定X", relevance_score=0.9),
        Evidence(source="条例B", excerpt="规定Y", relevance_score=0.8),
    ]
    state4 = add_evidence(state3, ev_list)
    check("add_evidence: 2 items", len(state4["evidence"]) == 2)
    check("add_evidence: source matches", state4["evidence"][0]["source"] == "条例A")

    # record_mcp_call
    mcp_record = MCPCallRecord(
        trace_id=state4["trace_id"], server_name="policy_server",
        tool_name="search_policy", input_args={"query": "开餐馆"},
        latency_ms=180.0,
    )
    state5 = record_mcp_call(state4, mcp_record)
    check("record_mcp_call: 1 record", len(state5["mcp_history"]) == 1)
    check("record_mcp_call: tool_name", state5["mcp_history"][0]["tool_name"] == "search_policy")

    # update_current_agent
    state6 = update_current_agent(state5, AgentName.POLICY)
    check("update_current_agent: policy", state6["current_agent"] == "policy")

    # transition_to
    state7 = transition_to(state6, NodeName.POLICY)
    check("transition_to: policy_node", state7["current_node"] == "policy_node")

    # set_final_answer
    state8 = set_final_answer(state7, "您需要先办理营业执照，再申请食品经营许可证。")
    check("set_final_answer", "营业执照" in state8["final_answer"])

    # set_error
    state9 = set_error(state8, "MCP policy_server connection timeout")
    check("set_error: message set", state9["error"] == "MCP policy_server connection timeout")
    check("set_error: history added", len(state9["error_history"]) == 1)
    check("set_error: agent in history", state9["error_history"][0]["agent"] == "policy")

    # clear_error
    state10 = clear_error(state9)
    check("clear_error: error cleared", state10["error"] == "")
    check("clear_error: retry_count == 1", state10["retry_count"] == 1)

    # ────────────────────────────────────────────────
    # 8. Type Hints 一致性
    # ────────────────────────────────────────────────
    section("8. Type Hints")

    hints = get_type_hints(AgentState)
    expected_fields = {
        "trace_id", "user_query", "intent", "intent_result",
        "task_plan", "current_agent", "current_node",
        "messages", "tool_calls", "mcp_history",
        "a2a_tasks", "waiting_task_id", "external_result",
        "evidence", "policy_result", "material_result",
        "final_answer", "risk_level", "safety_check",
        "execution_metrics", "error", "error_history", "retry_count",
    }
    check("AgentState has all 24 fields", set(hints.keys()) == expected_fields,
          f"missing: {expected_fields - set(hints.keys())}, extra: {set(hints.keys()) - expected_fields}")

    # Annotated 字段应保留在hints中
    check("task_plan in type hints", "task_plan" in hints)
    check("messages in type hints", "messages" in hints)
    check("tool_calls in type hints", "tool_calls" in hints)
    check("mcp_history in type hints", "mcp_history" in hints)
    check("a2a_tasks in type hints", "a2a_tasks" in hints)
    check("evidence in type hints", "evidence" in hints)
    check("error_history in type hints", "error_history" in hints)

    # ────────────────────────────────────────────────
    # 9. 综合场景 — 模拟完整执行流程
    # ────────────────────────────────────────────────
    section("9. End-to-End Scenario")

    # 用户发起请求
    s = create_initial_state(user_query="我在成都想开一家餐馆，需要哪些手续？")

    # Supervisor 规划
    task_a = Task(type="search_policy", agent=AgentName.POLICY,
                  description="查询餐饮许可政策")
    task_b = Task(type="check_material", agent=AgentName.MATERIAL,
                  description="检查所需材料清单",
                  dependencies=[task_a.id])
    task_c = Task(type="create_case", agent=AgentName.WORKFLOW,
                  description="创建营业执照办理件",
                  dependencies=[task_b.id])
    s = add_task(s, task_a)
    s = add_task(s, task_b)
    s = add_task(s, task_c)
    check("E2E: 3 tasks planned", len(s["task_plan"]) == 3)
    check("E2E: task_c depends on task_b",
          task_b.id in s["task_plan"][2].get("dependencies", s["task_plan"][2]["dependencies"]))

    # Policy Agent 执行
    s = update_current_agent(s, AgentName.POLICY)
    s = transition_to(s, NodeName.POLICY)
    s = record_mcp_call(s, MCPCallRecord(
        trace_id=s["trace_id"], server_name="policy_server",
        tool_name="search_policy",
        input_args={"query": "成都 开办餐馆 手续", "top_k": 5},
        latency_ms=230.0,
    ))
    ev = [Evidence(source="成都市餐饮服务许可管理办法", excerpt="第六条：申请餐饮服务许可证应当提交...",
                   relevance_score=0.94)]
    s = add_evidence(s, ev)
    check("E2E: policy agent evidence added", len(s["evidence"]) == 1)

    # Material Agent 执行
    s = update_current_agent(s, AgentName.MATERIAL)
    s = transition_to(s, NodeName.MATERIAL)
    s = record_mcp_call(s, MCPCallRecord(
        trace_id=s["trace_id"], server_name="material_server",
        tool_name="check_material",
        input_args={"business_type": "restaurant", "materials": ["身份证", "场地证明"]},
        output_result={"passed": True, "missing": []},
        latency_ms=150.0,
    ))
    check("E2E: material agent MCP call recorded", len(s["mcp_history"]) == 2)

    # Governance 检查
    guard = GuardrailResult(passed=True)
    s["safety_check"] = guard.model_dump()
    check("E2E: safety check passed", s["safety_check"]["passed"] is True)

    # 最终答案
    s = set_final_answer(s, "开办餐馆需要：1.营业执照 2.食品经营许可证 3.消防安全检查。请准备好身份证和经营场所证明。")
    check("E2E: final answer set", len(s["final_answer"]) > 0)
    check("E2E: trace_id intact throughout", s["trace_id"].startswith("trace_"))
    check("E2E: risk_level still low", s["risk_level"] == "low")

    # ────────────────────────────────────────────────
    # Summary
    # ────────────────────────────────────────────────
    section("SUMMARY")
    total = passed + failed
    print(f"\n  {passed}/{total} passed", end="")
    if failed > 0:
        print(f", {failed} FAILED")
        print(f"\n  Run with: python -m orchestration.langgraph.state")
        exit(1)
    else:
        print(f" — all good")
        print(f"\n  Run with: python -m orchestration.langgraph.state")
