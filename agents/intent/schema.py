"""
intent.schema - Intent Agent input/output data schemas

Author: le
Date: 2026/7/29
Version: 0.1
Task: Define Pydantic models for Intent Agent
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class IntentLabel(BaseModel):
    """单个意图标签"""

    label_id: str = Field(
        description="意图标签ID: business_license | restaurant_license | fund_query | ..."
    )
    label_name: str = Field(
        default="",
        description="标签中文名: 营业执照办理 | 餐饮许可 | ..."
    )
    category: str = Field(
        default="business",
        description="分类: business | personal | query | other"
    )


class IntentResult(BaseModel):
    """意图识别结果（与 orchestration.langgraph.state.IntentResult 对齐）"""

    label: str = Field(
        description="识别出的意图标签ID"
    )
    label_name: str = Field(
        default="",
        description="标签中文名"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="置信度，低于阈值触发 LLM fallback"
    )
    source: str = Field(
        default="keyword",
        description="识别来源: keyword | bert | llm"
    )


class IntentClassificationResult(BaseModel):
    """多分类结果（含所有候选）"""

    user_query: str = Field(description="用户原始输入")
    primary: IntentResult = Field(description="最可能的结果")
    candidates: list[IntentResult] = Field(
        default_factory=list,
        description="其他候选结果（按置信度降序）"
    )


# ============================================================
# 预定义标签表
# ============================================================

INTENT_LABELS: list[IntentLabel] = [
    IntentLabel(label_id="business_license", label_name="营业执照办理", category="business"),
    IntentLabel(label_id="restaurant_license", label_name="餐饮许可", category="business"),
    IntentLabel(label_id="business_register", label_name="企业注册", category="business"),
    IntentLabel(label_id="fund_query", label_name="公积金查询", category="personal"),
    IntentLabel(label_id="property_service", label_name="不动产服务", category="personal"),
    IntentLabel(label_id="medical_insurance", label_name="医保服务", category="personal"),
    IntentLabel(label_id="social_security", label_name="社保服务", category="personal"),
    IntentLabel(label_id="tax_service", label_name="税务服务", category="business"),
    IntentLabel(label_id="policy_query", label_name="政策咨询", category="query"),
    IntentLabel(label_id="other", label_name="其他事项", category="other"),
]
