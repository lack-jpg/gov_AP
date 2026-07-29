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
    A2A_CHECK = "a2a_check_node"


# ============================================================
# Pydantic Models — 子结构（强类型，序列化友好）
# ============================================================


class Task(BaseModel):
    """Supervisor拆解出的子任务"""

    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    type: str = Field(description="任务类型: search_policy | check_material | create_case | ...")
    agent: AgentName = Field(description="负责执行的Agent")
    description: str = Field(default="", description="任务描述")
    input: dict[str, Any] = Field(default_factory=dict, description="任务输入参数")
    dependencies: list[str] = Field(default_factory=list, description="依赖的前置任务ID列表")
    priority: int = Field(default=0, description="优先级，数字越大越优先")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = Field(default=None)


class Evidence(BaseModel):
    """政策证据引用（Policy Agent必须返回）"""

    source: str = Field(description="来源文件名或法规名称")
    excerpt: str = Field(description="引用的原文片段")
    page: Optional[int] = Field(default=None, description="页码")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0, description="相关性分数")


class PolicyResult(BaseModel):
    """Policy Agent检索结果"""

    answer: str = Field(description="基于政策的回答")
    evidence: list[Evidence] = Field(default_factory=list, description="证据引用列表")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="回答置信度")


class IntentResult(BaseModel):
    """Intent Agent识别结果"""

    label: str = Field(description="意图标签: business_license | fund_query | ...")
    label_name: str = Field(default="", description="标签中文名")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(default="bert", description="识别来源: bert | llm")


class MaterialCheckResult(BaseModel):
    """Material Agent审核结果"""

    passed: bool = Field(default=False)
    missing: list[str] = Field(default_factory=list, description="缺失的材料列表")
    warnings: list[str] = Field(default_factory=list, description="警告信息")
    extracted_fields: dict[str, Any] = Field(default_factory=dict, description="抽取到的字段")


class MCPCallRecord(BaseModel):
    """单次MCP工具调用记录"""

    trace_id: str
    server_name: str = Field(description="MCP Server名称: policy | material | workflow")
    tool_name: str = Field(description="工具名: search_policy | create_case | ...")
    input_args: dict[str, Any] = Field(default_factory=dict)
    output_result: Optional[dict[str, Any]] = Field(default=None)
    latency_ms: float = Field(default=0.0)
    status: MCPCallStatus = Field(default=MCPCallStatus.SUCCESS)
    error_message: Optional[str] = Field(default=None)
    called_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ToolCall(BaseModel):
    """Agent端的工具调用记录（LangGraph tool_calls追踪）"""

    tool_name: str
    tool_call_id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class A2ATaskRecord(BaseModel):
    """A2A跨域任务记录"""

    task_id: str = Field(default_factory=lambda: f"a2a_{uuid.uuid4().hex[:8]}")
    source_agent: str = Field(description="发起Agent")
    target_agent: str = Field(description="目标外部Agent: housing_agent | fund_agent | ...")
    skill: str = Field(description="调用的技能: query_property | query_fund | ...")
    input: dict[str, Any] = Field(default_factory=dict)
    artifact: Optional[dict[str, Any]] = Field(default=None, description="外部Agent返回结果")
    status: A2ATaskStatus = Field(default=A2ATaskStatus.CREATED)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)


class ExecutionMetrics(BaseModel):
    """单次Agent执行指标（用于Trace和Evaluation）"""

    trace_id: str
    agent_name: str
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    latency_ms: float = Field(default=0.0)
    tool_calls_count: int = Field(default=0)
    tool_errors_count: int = Field(default=0)
    step_count: int = Field(default=0)
    success: bool = Field(default=True)


class GuardrailResult(BaseModel):
    """安全护栏检测结果"""

    passed: bool = Field(default=True)
    pii_detected: list[str] = Field(default_factory=list)
    injection_detected: bool = Field(default=False)
    sensitive_words: list[str] = Field(default_factory=list)
    blocked: bool = Field(default=False)
    reason: Optional[str] = Field(default=None)


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
    """向task_plan追加一个子任务"""
    return {
        **state,
        "task_plan": [task.model_dump()],
    }


def add_evidence(state: AgentState, evidence_list: list[Evidence]) -> AgentState:
    """追加政策证据"""
    return {
        **state,
        "evidence": [e.model_dump() for e in evidence_list],
    }


def record_mcp_call(state: AgentState, record: MCPCallRecord) -> AgentState:
    """记录一次MCP调用"""
    return {
        **state,
        "mcp_history": [record.model_dump()],
    }


def set_error(state: AgentState, error_message: str) -> AgentState:
    """设置当前错误"""
    return {
        **state,
        "error": error_message,
        "error_history": [{
            "message": error_message,
            "agent": state.get("current_agent", ""),
            "node": state.get("current_node", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
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
