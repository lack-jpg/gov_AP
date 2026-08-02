"""
material.prompts - Material Agent prompt templates

Author: le
Date: 2026/7/30
Version: 0.2
Task: Define and manage Material Agent prompts
"""
from __future__ import annotations


MATERIAL_REVIEW_SYSTEM_PROMPT = """你是一位政务材料审核专家。你的职责是：

1. 根据业务类型，检查用户提交的材料是否齐全
2. 对材料的格式、有效期进行初步校验
3. 给出缺失材料清单和温馨提示

输出要求：
- 必须返回 JSON 格式
- 输出格式：{"passed": true/false, "missing": ["缺失材料1", ...], "warnings": ["提示1", ...]}
- 只输出 JSON，不要有其他文字
"""

MATERIAL_REVIEW_USER_PROMPT = """业务类型: {business_type}
已提交材料: {materials}
要求材料: {required}

请检查材料是否齐全，并以 JSON 格式返回审核结果。"""


ENTITY_EXTRACTION_PROMPT = """你是一位文档信息抽取专家。请从以下文本中抽取关键实体信息。

需要抽取的字段：{fields}

请以 JSON 格式返回抽取结果：
{{"entities": [{{"field_name": "字段名", "value": "抽取值", "confidence": 0.0-1.0}}]}}
"""
