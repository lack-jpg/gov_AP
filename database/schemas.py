"""
database.schemas - Pydantic schemas for database serialization/deserialization

Author: le
Date: 2026/7/29
Version: 0.1
Task: Define Pydantic v2 schemas for database models
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================
# Trace
# ============================================================


class TraceCreate(BaseModel):
    """创建 Trace 记录"""

    trace_id: str = Field(description="全链路追踪ID")
    span_id: str = Field(default="", description="当前 span ID")
    parent_span_id: Optional[str] = Field(default=None, description="父 span ID")
    agent_name: str = Field(description="Agent 名称")
    node_name: Optional[str] = Field(default=None, description="LangGraph 节点名称")
    input_data: Optional[str] = Field(default=None, description="Agent 输入（JSON）")
    output_data: Optional[str] = Field(default=None, description="Agent 输出（JSON）")
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    tool_input: Optional[str] = Field(default=None, description="工具调用参数")
    tool_output: Optional[str] = Field(default=None, description="工具调用返回")
    latency_ms: float = Field(default=0.0, description="执行耗时（毫秒）")
    input_tokens: int = Field(default=0, description="LLM 输入 Token 数")
    output_tokens: int = Field(default=0, description="LLM 输出 Token 数")
    status: str = Field(default="running", description="执行状态")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    risk_level: str = Field(default="low", description="风险等级")
    metadata_: Optional[dict[str, Any]] = Field(default=None, description="扩展元数据", alias="metadata")


class TraceResponse(BaseModel):
    """Trace 查询响应"""

    id: int = Field(description="主键ID")
    trace_id: str = Field(description="全链路追踪ID")
    agent_name: str = Field(description="Agent 名称")
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    latency_ms: float = Field(default=0.0, description="执行耗时")
    status: str = Field(default="running", description="执行状态")
    created_at: datetime = Field(description="记录创建时间")

    model_config = {"from_attributes": True}


# ============================================================
# Agent
# ============================================================


class AgentCreate(BaseModel):
    """注册新 Agent 配置"""

    name: str = Field(description="Agent 名称")
    version: str = Field(default="0.1.0", description="版本号")
    config: Optional[dict[str, Any]] = Field(default=None, description="Agent 配置 JSON")
    status: str = Field(default="active", description="Agent 状态")
    description: Optional[str] = Field(default=None, description="Agent 描述")


class AgentResponse(BaseModel):
    """Agent 配置查询响应"""

    agent_id: str = Field(description="Agent 唯一标识")
    name: str = Field(description="Agent 名称")
    version: str = Field(description="版本号")
    status: str = Field(description="Agent 状态")
    config: Optional[dict[str, Any]] = Field(default=None, description="配置 JSON")
    description: Optional[str] = Field(default=None, description="描述")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = {"from_attributes": True}


# ============================================================
# Prompt
# ============================================================


class PromptCreate(BaseModel):
    """创建 Prompt 版本"""

    agent_name: str = Field(description="关联的 Agent 名称")
    name: str = Field(description="Prompt 模板名称")
    version: str = Field(default="v1", description="版本号")
    content: str = Field(description="Prompt 模板内容")
    variables: Optional[list[str]] = Field(default=None, description="模板变量列表")
    is_active: bool = Field(default=True, description="是否为活跃版本")
    created_by: Optional[str] = Field(default=None, description="创建者")


class PromptResponse(BaseModel):
    """Prompt 查询响应"""

    prompt_id: str = Field(description="Prompt 唯一标识")
    agent_name: str = Field(description="关联的 Agent 名称")
    name: str = Field(description="Prompt 模板名称")
    version: str = Field(description="版本号")
    content: str = Field(description="Prompt 内容")
    is_active: bool = Field(description="是否活跃")
    created_at: datetime = Field(description="创建时间")

    model_config = {"from_attributes": True}


# ============================================================
# Evaluation
# ============================================================


class EvaluationCreate(BaseModel):
    """创建评测记录"""

    version: str = Field(description="被评测的版本号")
    task_success_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="任务成功率")
    tool_accuracy: float = Field(default=0.0, ge=0.0, le=1.0, description="工具选择准确率")
    rag_faithfulness: float = Field(default=0.0, ge=0.0, le=1.0, description="RAG 真实性")
    rag_answer_relevance: float = Field(default=0.0, ge=0.0, le=1.0, description="RAG 答案相关性")
    rag_context_recall: float = Field(default=0.0, ge=0.0, le=1.0, description="RAG 上下文召回率")
    avg_latency_ms: float = Field(default=0.0, description="平均耗时（毫秒）")
    avg_step_count: float = Field(default=0.0, description="平均执行步数")
    total_cases: int = Field(default=0, description="用例总数")
    passed_cases: int = Field(default=0, description="通过的用例数")
    report_json: Optional[dict[str, Any]] = Field(default=None, description="完整评测报告")
    dataset_name: Optional[str] = Field(default=None, description="数据集名称")


class EvaluationResponse(BaseModel):
    """评测记录响应"""

    eval_id: str = Field(description="评测唯一标识")
    version: str = Field(description="被评测的版本号")
    task_success_rate: float = Field(description="任务成功率")
    tool_accuracy: float = Field(description="工具选择准确率")
    rag_faithfulness: float = Field(description="RAG 真实性")
    avg_latency_ms: float = Field(description="平均耗时")
    total_cases: int = Field(description="用例总数")
    passed_cases: int = Field(description="通过的用例数")
    created_at: datetime = Field(description="评测时间")

    model_config = {"from_attributes": True}


# ============================================================
# Checkpoint
# ============================================================


class CheckpointCreate(BaseModel):
    """创建状态快照"""

    checkpoint_id: str = Field(description="Checkpoint 唯一标识")
    task_id: str = Field(description="关联的 A2A 任务 ID 或 trace_id")
    thread_id: str = Field(description="LangGraph thread_id")
    state_json: dict[str, Any] = Field(description="完整的 AgentState JSON")
    checkpoint_data: Optional[dict[str, Any]] = Field(default=None, description="LangGraph 原生 checkpoint 数据")
    status: str = Field(default="active", description="Checkpoint 状态")


class CheckpointResponse(BaseModel):
    """状态快照查询响应"""

    checkpoint_id: str = Field(description="Checkpoint 唯一标识")
    task_id: str = Field(description="关联的任务 ID")
    status: str = Field(description="状态")
    created_at: datetime = Field(description="创建时间")

    model_config = {"from_attributes": True}
