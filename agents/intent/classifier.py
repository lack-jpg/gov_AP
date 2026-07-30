"""
intent.classifier - BERT classifier for intent recognition

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement BERT fine-tuning and inference for intent classification
"""
from __future__ import annotations

import os
from typing import Optional

from agents.intent.schema import IntentResult, INTENT_LABELS
from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 关键词→意图映射表（BERT 模型不可用时的兜底方案）
# ============================================================

_KEYWORD_MAP: dict[str, str] = {
    # 餐饮
    "餐馆": "restaurant_license",
    "餐饮": "restaurant_license",
    "饭店": "restaurant_license",
    "餐厅": "restaurant_license",
    "食品": "restaurant_license",
    # 公司/企业
    "公司": "business_register",
    "企业": "business_register",
    "注册": "business_register",
    "营业执照": "business_license",
    "执照": "business_license",
    "个体户": "business_license",
    # 公积金
    "公积金": "fund_query",
    "住房": "fund_query",
    # 不动产
    "房产": "property_service",
    "不动产": "property_service",
    "房屋": "property_service",
    "产权": "property_service",
    "过户": "property_service",
    # 医保
    "医保": "medical_insurance",
    "医疗": "medical_insurance",
    "报销": "medical_insurance",
    # 社保
    "社保": "social_security",
    "养老": "social_security",
    # 税务
    "税": "tax_service",
    "发票": "tax_service",
    "纳税": "tax_service",
}


# ============================================================
# Classifier
# ============================================================


class IntentClassifier:
    """
    意图分类器。

    策略（按优先级）：
    1. BERT 模型推理（TODO: 加载 fine-tuned 模型）
    2. 关键词匹配（兜底，始终可用）
    3. LLM fallback（由 IntentAgent 调用）

    使用方式:
        classifier = IntentClassifier()
        result = classifier.classify("我要开一家餐馆")
        # IntentResult(label="restaurant_license", confidence=0.85)
    """

    # BERT 推理的置信度阈值，低于此值触发 LLM fallback
    BERT_CONFIDENCE_THRESHOLD: float = 0.7

    def __init__(self, model_path: Optional[str] = None):
        """
        Args:
            model_path: fine-tuned BERT 模型本地路径。
                        默认从环境变量 INTENT_MODEL_PATH 解析。
                        不传且本地路径不存在时使用关键词匹配。
        """
        self._model_path = model_path or self._resolve_path()
        self._model = None

        # 构建标签名映射
        self._label_names: dict[str, str] = {
            lbl.label_id: lbl.label_name for lbl in INTENT_LABELS
        }

    async def classify(self, text: str) -> IntentResult:
        """
        对文本进行意图分类。

        Args:
            text: 用户输入的自然语言文本

        Returns:
            IntentResult
        """
        # 1. BERT 推理（如果模型已加载）
        if self._model is not None:
            try:
                return await self._bert_classify(text)
            except Exception as e:
                logger.warning("BERT 推理失败，降级到关键词匹配: {}", e)

        # 2. 关键词匹配（兜底）
        return self._keyword_classify(text)

    async def classify_or_none(self, text: str) -> Optional[IntentResult]:
        """
        分类并返回结果，仅当置信度足够高时返回（否则返回 None）。

        用于判断是否需要 LLM fallback。
        """
        result = await self.classify(text)
        if result.confidence >= self.BERT_CONFIDENCE_THRESHOLD:
            return result
        return None

    # ── BERT 推理 ──

    async def _bert_classify(self, text: str) -> IntentResult:
        """
        使用 fine-tuned BERT 模型推理。

        TODO: 实现真实 BERT 推理
        - model = AutoModelForSequenceClassification.from_pretrained(path)
        - tokenizer = AutoTokenizer.from_pretrained(path)
        - inputs = tokenizer(text, return_tensors="pt")
        - outputs = model(**inputs)
        - probs = softmax(outputs.logits)
        """
        # 当前 stub: 用关键词结果模拟
        kw_result = self._keyword_classify(text)
        return IntentResult(
            label=kw_result.label,
            label_name=kw_result.label_name,
            confidence=0.92,  # 模拟高置信度
            source="bert",
        )

    # ── 关键词匹配 ──

    def _keyword_classify(self, text: str) -> IntentResult:
        """
        基于关键词表匹配意图（始终可用）。

        Args:
            text: 用户输入文本

        Returns:
            IntentResult
        """
        # 计算每个标签的匹配分数
        scores: dict[str, int] = {}
        for keyword, label in _KEYWORD_MAP.items():
            if keyword in text:
                scores[label] = scores.get(label, 0) + 1

        if not scores:
            return IntentResult(
                label="policy_query",
                label_name=self._label_names.get("policy_query", "政策咨询"),
                confidence=0.5,
                source="keyword",
            )

        # 取最高分
        best = max(scores, key=scores.get)
        match_count = scores[best]
        confidence = min(0.6 + match_count * 0.1, 0.85)

        return IntentResult(
            label=best,
            label_name=self._label_names.get(best, best),
            confidence=confidence,
            source="keyword",
        )

    # ── 模型管理 ──

    def load_model(self, model_path: str) -> None:
        """
        加载 fine-tuned BERT 模型。

        Args:
            model_path: 模型文件路径（本地目录）
        """
        self._model_path = model_path
        # TODO: self._model = AutoModelForSequenceClassification.from_pretrained(model_path)
        # TODO: self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        logger.info("BERT 模型已加载（stub）: {}", model_path)

    @staticmethod
    def _resolve_path() -> Optional[str]:
        """从环境变量解析本地模型路径，存在则返回"""
        path = os.environ.get("INTENT_MODEL_PATH", "models/intent/bert-intent")
        if os.path.isdir(path):
            return path
        return None

    @property
    def is_model_loaded(self) -> bool:
        """BERT 模型是否已加载"""
        return self._model is not None

    @property
    def model_path(self) -> Optional[str]:
        """本地模型路径"""
        return self._model_path
