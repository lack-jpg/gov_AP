"""
backend.api.schemas - API request/response Pydantic schemas

Author: le
Date: 2026/7/29
Version: 0.1
Task: Define API-level Pydantic models for request validation and response serialization
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================
# Request Models
# ============================================================


class ChatRequest(BaseModel):
    """用户对话请求"""

    user_query: str = Field(
        description="用户自然语言输入，如 '我想在成都开一家餐馆需要什么手续'",
        min_length=1,
    )
    user_id: str = Field(
        description="用户唯一标识，用于权限控制和会话关联",
    )
    trace_id: Optional[str] = Field(
        default=None,
        description="链路追踪ID，不传则自动生成 (trace_xxxxxxxxxxxxxxxx)",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="多轮对话会话ID，用于关联上下文",
    )


class AgentStatusRequest(BaseModel):
    """Agent执行状态查询请求"""

    trace_id: str = Field(
        description="要查询的链路追踪ID",
    )


class A2ACallbackRequest(BaseModel):
    """A2A外部Agent回调请求"""

    task_id: str = Field(
        description="A2A任务ID，与发送任务时的task_id关联",
    )
    status: str = Field(
        description="任务完成状态: completed | failed | timeout",
    )
    artifact: Optional[dict[str, Any]] = Field(
        default=None,
        description="外部Agent返回的结果数据，失败时为None",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="任务失败时的错误信息",
    )


class EvaluationRequest(BaseModel):
    """评测请求"""

    version: Optional[str] = Field(
        default=None,
        description="要评测的版本号，不传则评测当前版本",
    )
    dataset: Optional[str] = Field(
        default=None,
        description="指定评测数据集路径，不传则使用全部cases/*.json",
    )


# ============================================================
# Response Models
# ============================================================


class EvidenceItem(BaseModel):
    """回答中引用的政策证据"""

    source: str = Field(
        description="来源文件名或法规名称",
    )
    excerpt: str = Field(
        description="引用原文片段",
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="相关性分数",
    )


class ChatResponse(BaseModel):
    """用户对话响应"""

    trace_id: str = Field(
        description="本次请求的链路追踪ID",
    )
    answer: str = Field(
        description="多Agent协同产生的最终回答（自然语言）",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="回答引用的政策证据列表",
    )
    intent: str = Field(
        default="",
        description="识别出的用户意图标签",
    )
    risk_level: str = Field(
        default="low",
        description="本次回答的风险等级: low | medium | high | critical",
    )
    execution_steps: int = Field(
        default=0,
        description="Agent执行的总步数",
    )
    elapsed_ms: float = Field(
        default=0.0,
        description="从请求到响应总耗时（毫秒）",
    )
    error: Optional[str] = Field(
        default=None,
        description="执行过程中的错误信息，无错误时为None",
    )


class AgentStatusResponse(BaseModel):
    """Agent执行状态响应"""

    trace_id: str = Field(
        description="链路追踪ID",
    )
    status: str = Field(
        description="当前状态: pending | running | completed | failed",
    )
    current_node: str = Field(
        default="",
        description="当前执行到的LangGraph节点名称",
    )
    current_agent: str = Field(
        default="",
        description="当前正在执行的Agent名称",
    )
    steps_completed: int = Field(
        default=0,
        description="已完成的执行步数",
    )
    final_answer: Optional[str] = Field(
        default=None,
        description="最终答案，执行完成前为None",
    )


class A2ACallbackResponse(BaseModel):
    """A2A回调响应"""

    success: bool = Field(
        default=True,
        description="回调处理是否成功",
    )
    message: str = Field(
        default="callback processed",
        description="处理结果消息",
    )


class DashboardOverview(BaseModel):
    """运维看板概览"""

    total_requests: int = Field(
        default=0,
        description="总请求数",
    )
    success_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="请求成功率",
    )
    avg_latency_ms: float = Field(
        default=0.0,
        description="平均响应耗时（毫秒）",
    )
    active_agents: int = Field(
        default=0,
        description="当前活跃Agent数",
    )
    tool_call_count: int = Field(
        default=0,
        description="MCP工具调用总次数",
    )
    a2a_task_count: int = Field(
        default=0,
        description="A2A跨域任务总数",
    )


class EvaluationMetricsResponse(BaseModel):
    """评测指标响应"""

    version: str = Field(
        description="评测版本号",
    )
    task_success_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="任务成功率",
    )
    rag_faithfulness: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="RAG回答真实性",
    )
    rag_answer_relevance: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="RAG答案相关性",
    )
    tool_accuracy: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="工具选择准确率",
    )
    avg_latency_ms: float = Field(
        default=0.0,
        description="平均响应耗时（毫秒）",
    )
    avg_step_count: float = Field(
        default=0.0,
        description="平均执行步数",
    )


class ErrorResponse(BaseModel):
    """错误响应（统一格式）"""

    error: str = Field(
        description="错误类型",
    )
    message: str = Field(
        description="错误详情消息",
    )
    trace_id: Optional[str] = Field(
        default=None,
        description="关联的链路追踪ID",
    )
    detail: Optional[str] = Field(
        default=None,
        description="附加错误详情（仅debug模式）",
    )
