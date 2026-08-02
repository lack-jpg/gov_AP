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
    # 餐饮（覆盖常见业态）
    "餐馆": "restaurant_license",
    "餐饮": "restaurant_license",
    "饭店": "restaurant_license",
    "餐厅": "restaurant_license",
    "食品": "restaurant_license",
    "菜馆": "restaurant_license",     # 川菜馆/湘菜馆/粤菜馆
    "面馆": "restaurant_license",
    "小吃": "restaurant_license",
    "咖啡": "restaurant_license",
    "奶茶": "restaurant_license",
    "烧烤": "restaurant_license",
    "火锅": "restaurant_license",
    "食堂": "restaurant_license",
    "外卖": "restaurant_license",
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
    1. BERT 模型推理（当本地模型存在且已加载）
    2. 关键词匹配（兜底，始终可用）
    3. LLM fallback（由 IntentAgent 调用）

    使用方式:
        classifier = IntentClassifier()
        result = classifier.classify("我要开一家餐馆")
        # IntentResult(label="restaurant_license", confidence=0.85)
    """

    # BERT 推理的置信度阈值，低于此值触发 LLM fallback
    BERT_CONFIDENCE_THRESHOLD: float = 0.7

    def __init__(
        self,
        model_path: Optional[str] = None,
        auto_load: bool = True,
    ):
        """
        Args:
            model_path: fine-tuned BERT 模型本地路径。
                        默认从环境变量 INTENT_MODEL_PATH 解析。
                        不传且本地路径不存在时使用关键词匹配。
            auto_load: 若模型路径存在则自动加载（transformers）。
                       默认 True；测试环境可显式关闭以加速。
        """
        self._model_path = model_path or self._resolve_path()
        self._model = None
        self._tokenizer = None
        # label_id 索引 → 意图标签（与模型 config.id2label 对齐）
        self._id2label: dict[int, str] = {
            i: lbl.label_id for i, lbl in enumerate(INTENT_LABELS)
        }

        # 构建标签名映射
        self._label_names: dict[str, str] = {
            lbl.label_id: lbl.label_name for lbl in INTENT_LABELS
        }

        # 本地模型存在时自动加载真实 BERT
        if auto_load and self._model_path and os.path.isdir(self._model_path):
            self.load_model(self._model_path)

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

        - model = AutoModelForSequenceClassification.from_pretrained(path)
        - tokenizer = AutoTokenizer.from_pretrained(path)
        - inputs = tokenizer(text, return_tensors="pt")
        - outputs = model(**inputs)
        - probs = softmax(outputs.logits)

        模型未加载时降级到关键词匹配，且 source 标记为 keyword
        （不再伪造 source="bert"）。
        """
        if self._model is None or self._tokenizer is None:
            kw_result = self._keyword_classify(text)
            logger.info("BERT 模型未加载，使用关键词匹配: {}", text[:30])
            return kw_result

        try:
            import asyncio
            return await asyncio.to_thread(self._bert_infer_sync, text)
        except Exception as e:
            logger.warning("BERT 推理失败，降级到关键词匹配: {}", e)
            return self._keyword_classify(text)

    def _bert_infer_sync(self, text: str) -> IntentResult:
        """
        同步 BERT 推理（在 asyncio.to_thread 中运行，避免阻塞事件循环）。
        """
        import torch

        inputs = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=64,
            padding=True,
        )

        with torch.no_grad():
            outputs = self._model(**inputs)

        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
        label_idx = int(torch.argmax(probs, dim=-1))
        confidence = float(probs[0][label_idx])
        label = self._id2label.get(label_idx, "other")

        return IntentResult(
            label=label,
            label_name=self._label_names.get(label, label),
            confidence=confidence,
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

        使用 transformers 从本地路径加载模型和 tokenizer。
        加载失败时回退到关键词匹配（不中断流程）。

        Args:
            model_path: 模型文件路径（本地目录）
        """
        self._model_path = model_path

        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )

            self._tokenizer = AutoTokenizer.from_pretrained(model_path)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                model_path
            )

            # 对齐模型 config 的 id2label（若存在）
            if self._model.config.id2label:
                self._id2label = {
                    int(k): str(v) for k, v in self._model.config.id2label.items()
                }

            logger.info("BERT 模型已加载: {} (labels={})", model_path, len(self._id2label))
        except Exception as e:
            logger.warning("BERT 模型加载失败，使用关键词匹配: {}", e)
            self._model = None
            self._tokenizer = None

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
