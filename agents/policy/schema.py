"""
policy.schema - Policy Agent input/output data schemas (answer + evidence)

Author: le
Date: 2026/7/29
Version: 0.1
Task: Define Pydantic models for Policy Agent
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PolicyDocument(BaseModel):
    """单条政策文档"""

    title: str = Field(description="文档标题")
    content: str = Field(description="文档内容")
    source: str = Field(description="来源：文件名或法规名")
    page: int | None = Field(default=None, description="页码")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="检索相关性分数")


class PolicyEvidence(BaseModel):
    """政策证据引用"""

    source: str = Field(description="来源文件名或法规名称")
    excerpt: str = Field(description="引用原文片段")
    page: int | None = Field(default=None, description="页码范围")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0, description="相关性分数")


class PolicyResult(BaseModel):
    """Policy Agent 检索结果（与 state.py 中的定义对齐）"""

    answer: str = Field(description="基于政策生成的回答")
    evidence: list[PolicyEvidence] = Field(default_factory=list, description="证据引用列表")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="回答置信度")
    retrieved_count: int = Field(default=0, description="检索到的文档总数")
