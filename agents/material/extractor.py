"""
material.extractor - Entity extraction: extract key fields from documents

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement entity/field extraction using regex patterns (stub mode)
"""
from __future__ import annotations

import re
from typing import Any

from tools.logger import get_logger

logger = get_logger(__name__)


class EntityExtractor:
    """
    实体/字段抽取器。

    当前为 stub 实现：使用正则表达式提取常见政务字段。
    Phase 3 接入 NER 模型（如 bert-base-chinese-NER）。

    使用方式:
        extractor = EntityExtractor()
        entities = await extractor.extract(text, schema={"name": "姓名", "id_card": "身份证号"})
    """

    # ── 预定义提取模式 ──
    DEFAULT_PATTERNS: dict[str, tuple[str, str]] = {
        "name": (r"申请人[：:]\s*([^\n]{2,4})", "姓名"),
        "id_card": (r"身份证号[：:]\s*(\d{17}[\dXx])", "身份证号"),
        "phone": (r"(?:电话|手机|联系电话)[：:]\s*(1\d{10})", "手机号"),
        "address": (r"(?:地址|联系地址)[：:]\s*([^\n]{5,50})", "联系地址"),
        "business_type": (r"申请事项[：:]\s*([^\n]{2,20})", "申请事项"),
        "unified_code": (r"统一社会信用代码[：:]\s*([A-Za-z0-9]{18})", "统一社会信用代码"),
    }

    def __init__(self, model_path: str = ""):
        """
        Args:
            model_path: NER 模型路径（Phase 3 使用）
        """
        self._model_path = model_path

    async def extract(
        self,
        text: str,
        field_schema: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        从文本中抽取指定字段的实体。

        Args:
            text: OCR 后的文本
            field_schema: 需要抽取的字段定义 {field_name: field_label}，
                          不传则使用默认模式

        Returns:
            实体列表 [{field_name, field_label, value, confidence}]
        """
        entities: list[dict[str, Any]] = []

        if field_schema:
            # 按传入的 schema 提取
            for field_name, field_label in field_schema.items():
                pattern_info = self.DEFAULT_PATTERNS.get(field_name)
                if pattern_info:
                    pattern, _ = pattern_info
                    match = re.search(pattern, text)
                    if match:
                        entities.append({
                            "field_name": field_name,
                            "field_label": field_label,
                            "value": match.group(1),
                            "confidence": 0.85,
                        })
                else:
                    # 未知字段，尝试通用模式
                    generic_pattern = rf"{field_label}[：:]\s*([^\n]{{2,50}})"
                    match = re.search(generic_pattern, text)
                    if match:
                        entities.append({
                            "field_name": field_name,
                            "field_label": field_label,
                            "value": match.group(1),
                            "confidence": 0.5,
                        })
        else:
            # 使用默认模式提取所有已知字段
            for field_name, (pattern, field_label) in self.DEFAULT_PATTERNS.items():
                match = re.search(pattern, text)
                if match:
                    entities.append({
                        "field_name": field_name,
                        "field_label": field_label,
                        "value": match.group(1),
                        "confidence": 0.85,
                    })

        logger.info("EntityExtractor: extracted {} entities from {} chars", len(entities), len(text))
        return entities

    @staticmethod
    def mask_pii(text: str) -> str:
        """
        对文本中的 PII 进行脱敏处理。

        Args:
            text: 原始文本

        Returns:
            脱敏后的文本
        """
        # 手机号脱敏
        text = re.sub(r'(1\d{2})\d{4}(\d{4})', r'\1****\2', text)
        # 身份证号脱敏
        text = re.sub(r'(\d{6})\d{8}(\d{3}[\dXx])', r'\1********\2', text)
        return text
