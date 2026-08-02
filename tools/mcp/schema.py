"""
mcp.schema - MCP Tool JSON Schema definitions for all tools

Author: le
Date: 2026/7/30
Version: 0.2
Task: Define Pydantic v2 Input/Output models and tool registry for all 6 MCP tools
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================
# Policy Server — search_policy
# ============================================================


class SearchPolicyInput(BaseModel):
    """search_policy 工具输入参数"""

    query: str = Field(
        description="用户查询文本",
        min_length=1,
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="返回的政策文档数量",
    )


class PolicyDocument(BaseModel):
    """单条政策文档"""

    document_id: str = Field(description="文档唯一标识")
    title: str = Field(description="政策标题")
    content: str = Field(description="政策内容摘要")
    source: str = Field(description="来源法规/文件名")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="相关性分数")


class SearchPolicyOutput(BaseModel):
    """search_policy 工具输出"""

    documents: list[PolicyDocument] = Field(default_factory=list, description="匹配的政策文档列表")
    total_found: int = Field(default=0, description="匹配总数")


# ============================================================
# Policy Server — get_policy_detail
# ============================================================


class GetPolicyDetailInput(BaseModel):
    """get_policy_detail 工具输入参数"""

    document_id: str = Field(description="政策文档ID")


class GetPolicyDetailOutput(BaseModel):
    """get_policy_detail 工具输出"""

    document_id: str = Field(description="文档唯一标识")
    title: str = Field(description="政策标题")
    content: str = Field(description="政策全文")
    source: str = Field(description="来源法规/文件名")
    publish_date: str = Field(default="", description="发布日期")
    department: str = Field(default="", description="发布部门")


# ============================================================
# Material Server — extract_entity
# ============================================================


class ExtractEntityInput(BaseModel):
    """extract_entity 工具输入参数"""

    file_id: str = Field(description="文件唯一标识")
    field_schema: Optional[dict[str, str]] = Field(
        default=None,
        description="需要提取的字段定义",
        alias="schema",
    )


class ExtractedEntity(BaseModel):
    """单个提取出的实体"""

    field_name: str = Field(description="字段名")
    field_label: str = Field(description="字段中文名")
    value: str = Field(description="提取值")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")


class ExtractEntityOutput(BaseModel):
    """extract_entity 工具输出"""

    file_id: str = Field(description="处理的文件ID")
    entities: list[ExtractedEntity] = Field(default_factory=list, description="提取出的实体列表")
    raw_text_preview: str = Field(default="", description="OCR原始文本前200字预览")


# ============================================================
# Material Server — check_material
# ============================================================


class CheckMaterialInput(BaseModel):
    """check_material 工具输入参数"""

    business_type: str = Field(
        description="业务类型: restaurant_license | business_license | business_register | property_service | fund_query",
    )
    materials: list[str] = Field(
        default_factory=list,
        description="已提交的材料名称列表",
    )


class CheckMaterialOutput(BaseModel):
    """check_material 工具输出"""

    passed: bool = Field(description="材料是否齐全")
    missing: list[str] = Field(default_factory=list, description="缺失材料")
    submitted: list[str] = Field(default_factory=list, description="已提交材料")
    required: list[str] = Field(default_factory=list, description="要求材料清单")
    warnings: list[str] = Field(default_factory=list, description="温馨提示")


# ============================================================
# Workflow Server — create_case
# ============================================================


class CreateCaseInput(BaseModel):
    """create_case 工具输入参数"""

    user_id: str = Field(description="用户唯一标识")
    service: str = Field(description="服务类型（对应 intent 标签）")
    materials: Optional[list[str]] = Field(default=None, description="已提交材料列表")


class CreateCaseOutput(BaseModel):
    """create_case 工具输出"""

    case_id: str = Field(description="办件编号")
    status: str = Field(description="办件状态: created")
    service: str = Field(description="服务类型")
    user_id: str = Field(description="用户ID")
    created_at: str = Field(description="创建时间 ISO 8601 UTC")


# ============================================================
# Workflow Server — query_status
# ============================================================


class QueryStatusInput(BaseModel):
    """query_status 工具输入参数"""

    case_id: str = Field(description="要查询的办件编号")


class QueryStatusOutput(BaseModel):
    """query_status 工具输出"""

    case_id: str = Field(description="办件编号")
    status: str = Field(description="当前状态")
    progress: str = Field(description="进度描述")
    updated_at: str = Field(description="最后更新时间 ISO 8601 UTC")


# ============================================================
# 通用 Gateway 请求/响应模型
# ============================================================


class ToolCallRequest(BaseModel):
    """Gateway ↔ Server 工具调用请求"""

    server_name: str = Field(description="目标 MCP Server 名称")
    tool_name: str = Field(description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="调用参数")
    trace_id: str = Field(default="", description="链路追踪ID")


class ToolCallResponse(BaseModel):
    """工具调用响应"""

    success: bool = Field(default=True)
    result: Optional[dict[str, Any]] = Field(default=None)
    error: Optional[str] = Field(default=None)
    server_name: str = Field(default="")
    tool_name: str = Field(default="")


class ToolListResponse(BaseModel):
    """工具列表响应"""

    server_name: str = Field(description="Server 名称")
    tools: list[dict[str, Any]] = Field(default_factory=list, description="工具定义列表")


# ============================================================
# Tool Registry — 全局工具注册表
# ============================================================


TOOL_REGISTRY: dict[str, list[dict[str, Any]]] = {
    "policy_server": [
        {
            "name": "search_policy",
            "description": "搜索政策文档，根据用户查询返回相关的政策和法规信息",
            "input_schema": SearchPolicyInput.model_json_schema(),
            "output_schema": SearchPolicyOutput.model_json_schema(),
        },
        {
            "name": "get_policy_detail",
            "description": "获取指定政策文档的详细完整内容",
            "input_schema": GetPolicyDetailInput.model_json_schema(),
            "output_schema": GetPolicyDetailOutput.model_json_schema(),
        },
    ],
    "material_server": [
        {
            "name": "extract_entity",
            "description": "从材料文件中通过OCR抽取结构化字段信息",
            "input_schema": ExtractEntityInput.model_json_schema(),
            "output_schema": ExtractEntityOutput.model_json_schema(),
        },
        {
            "name": "check_material",
            "description": "检查材料完整性，判断是否满足业务要求",
            "input_schema": CheckMaterialInput.model_json_schema(),
            "output_schema": CheckMaterialOutput.model_json_schema(),
        },
    ],
    "workflow_server": [
        {
            "name": "create_case",
            "description": "创建新的政务办件，返回办件编号",
            "input_schema": CreateCaseInput.model_json_schema(),
            "output_schema": CreateCaseOutput.model_json_schema(),
        },
        {
            "name": "query_status",
            "description": "查询指定办件的当前处理状态和进度",
            "input_schema": QueryStatusInput.model_json_schema(),
            "output_schema": QueryStatusOutput.model_json_schema(),
        },
    ],
}
