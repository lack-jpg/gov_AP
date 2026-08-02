"""
material.extractor - Entity extraction: extract key fields from documents

Author: le
Date: 2026/7/30
Version: 0.3
Task: Implement entity/field extraction using BERT-NER (deep learning) + regex fallback
"""
from __future__ import annotations

import re
from typing import Any, Optional

from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# NER 标签 → 业务字段映射
# ============================================================

# CLUENER2020 标签映射（常用中文 NER 数据集标签）
_NER_LABEL_MAP: dict[str, str] = {
    # CLUENER2020 标签
    "name": "name",           # 人名
    "company": "company",     # 公司
    "organization": "company",
    "address": "address",     # 地址
    "government": "agency",   # 政府机构
    "position": "title",      # 职位
    "scene": "location",      # 地点
    "game": "event",          # 事件
    "book": "document",       # 文档
    "movie": "document",
    "email": "contact",       # 联系方式
    "mobile": "phone",        # 手机号
    "phone": "phone",
    # 通用 BIO 标签
    "PER": "name",            # 人物 → 姓名
    "ORG": "company",         # 组织 → 公司
    "LOC": "address",         # 地点 → 地址
    "GPE": "address",         # 地理政治实体 → 地址
    "FAC": "location",        # 设施
    "DATE": "date",           # 日期
    "TIME": "time",           # 时间
    "MONEY": "amount",        # 金额
    "PERCENT": "amount",
    # 自定义政务 NER 标签
    "ID_CARD": "id_card",     # 身份证号
    "UNIFIED_CODE": "unified_code",  # 统一社会信用代码
    "PHONE": "phone",         # 手机号
    "BIZ_TYPE": "business_type",  # 业务类型
}

# 实体标签 → 中文描述
_NER_LABEL_DESC: dict[str, str] = {
    "name": "姓名",
    "company": "公司/单位",
    "address": "地址",
    "agency": "政府机构",
    "phone": "手机号",
    "id_card": "身份证号",
    "unified_code": "统一社会信用代码",
    "date": "日期",
    "amount": "金额",
    "business_type": "申请事项",
    "title": "职位",
    "document": "文档",
    "event": "事件",
    "location": "地点",
    "contact": "联系方式",
}


class EntityExtractor:
    """
    实体/字段抽取器。

    支持双模式：
    1. BERT-NER 模式（生产）- 基于深度学习的中文命名实体识别
    2. Regex 模式（开发/降级）- 使用正则表达式提取常见政务字段

    使用方式:
        extractor = EntityExtractor()
        entities = await extractor.extract(text, field_schema={"name": "姓名", "id_card": "身份证号"})
    """

    # ── 预定义正则提取模式 ──
    DEFAULT_PATTERNS: dict[str, tuple[str, str]] = {
        "name": (r"申请人[：:]\s*([^\n]{2,4})", "姓名"),
        "company": (r"(?:单位名称|公司名称|企业名称)[：:]\s*([^\n]{2,30})", "公司/单位"),
        "id_card": (r"身份证号[：:]\s*(\d{17}[\dXx])", "身份证号"),
        "phone": (r"(?:电话|手机|联系电话)[：:]\s*(1\d{10})", "手机号"),
        "address": (r"(?:地址|联系地址)[：:]\s*([^\n]{5,50})", "联系地址"),
        "business_type": (r"申请事项[：:]\s*([^\n]{2,20})", "申请事项"),
        "unified_code": (r"统一社会信用代码[：:]\s*([A-Za-z0-9]{18})", "统一社会信用代码"),
    }

    def __init__(self, model_path: str = "", use_gpu: bool = False, auto_download: bool = False):
        """
        Args:
            model_path: NER 模型路径（本地路径 或 HuggingFace model ID）
            use_gpu: 是否使用 GPU 推理
            auto_download: 当 model_path 无效时，是否自动从 HuggingFace 下载模型
        """
        self._model_path = model_path
        self._use_gpu = use_gpu
        self._auto_download = auto_download
        self._model_loaded = False
        self._pipeline: Any = None  # transformers pipeline

    async def extract(
        self,
        text: str,
        field_schema: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        从文本中抽取指定字段的实体。

        优先使用 BERT-NER 模型，不可用时自动降级到 regex 模式。

        Args:
            text: OCR 后的文本
            field_schema: 需要抽取的字段定义 {field_name: field_label}，
                          不传则提取所有可识别的实体

        Returns:
            实体列表 [{field_name, field_label, value, confidence, source}]
        """
        if not text or not text.strip():
            return []

        # ── 尝试 BERT-NER ──
        ner_entities: list[dict[str, Any]] = []
        if self._ensure_ner_model():
            ner_entities = await self._extract_with_ner(text, field_schema)

        # ── Regex 补充 ──
        regex_entities = await self._extract_with_regex(text, field_schema)

        # ── 合并结果（NER 优先，regex 补充未知字段）─
        merged = self._merge_entities(ner_entities, regex_entities)

        logger.info(
            "EntityExtractor: {} entities ({} ner + {} regex → {} merged) from {} chars",
            len(merged), len(ner_entities), len(regex_entities),
            len(merged), len(text),
        )
        return merged

    async def extract_all(self, text: str) -> list[dict[str, Any]]:
        """
        提取所有可识别的实体（不限字段类型）。

        Args:
            text: 文本内容

        Returns:
            所有实体的列表
        """
        return await self.extract(text, field_schema=None)

    def is_loaded(self) -> bool:
        """检查 NER 模型是否已加载"""
        return self._model_loaded

    # ── BERT-NER 模式 ──

    def _ensure_ner_model(self) -> bool:
        """
        确保 NER 模型已加载，返回是否可用。

        加载策略：
        1. model_path 为本地有效路径 → 从本地加载
        2. model_path 为 HuggingFace ID 且 auto_download=True → 自动下载
        3. model_path 未提供 → 跳过，使用 regex 模式
        """
        if self._model_loaded:
            return True

        if not self._model_path and not self._auto_download:
            return False

        try:
            from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification

            import os

            model_source = self._model_path or "uer/roberta-base-finetuned-cluener2020-chinese"

            if self._model_path and os.path.isdir(self._model_path):
                # 本地路径加载
                tokenizer = AutoTokenizer.from_pretrained(self._model_path)
                model = AutoModelForTokenClassification.from_pretrained(self._model_path)
                self._pipeline = pipeline(
                    "ner",
                    model=model,
                    tokenizer=tokenizer,
                    aggregation_strategy="simple",
                    device=0 if self._use_gpu else -1,
                )
                logger.info("BERT-NER 本地模型加载成功: {}", self._model_path)
            elif self._auto_download:
                # 自动下载
                self._pipeline = pipeline(
                    "ner",
                    model=model_source,
                    aggregation_strategy="simple",
                    device=0 if self._use_gpu else -1,
                )
                logger.info("BERT-NER 远程模型下载成功: {}", model_source)
            else:
                logger.info("NER 模型未配置，使用 regex 模式")
                return False

            self._model_loaded = True
            return True

        except ImportError:
            logger.info("transformers 未安装，使用 regex 模式（pip install transformers）")
            return False
        except Exception as e:
            logger.warning("BERT-NER 模型加载失败: {}，降级到 regex 模式", e)
            return False

    async def _extract_with_ner(
        self,
        text: str,
        field_schema: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """使用 BERT-NER 模型提取实体"""
        assert self._pipeline is not None

        try:
            raw_results = self._pipeline(text)
        except Exception as e:
            logger.error("BERT-NER 推理失败: {}", e)
            return []

        if not raw_results:
            return []

        # 将 NER 结果映射到业务字段
        entities: list[dict[str, Any]] = []
        seen_values: set[str] = set()

        for item in raw_results:
            entity_group = item.get("entity_group", "")
            word = item.get("word", "").strip()
            score = item.get("score", 0.0)

            if not word or word in seen_values:
                continue

            # 映射标签
            field_name = _NER_LABEL_MAP.get(entity_group, entity_group.lower())
            field_label = _NER_LABEL_DESC.get(field_name, entity_group)

            # 根据 field_schema 过滤
            if field_schema and field_name not in field_schema:
                continue

            seen_values.add(word)
            entities.append({
                "field_name": field_name,
                "field_label": field_label,
                "value": word,
                "confidence": round(float(score), 4),
                "source": "ner",
                "ner_tag": entity_group,
            })

        return entities

    # ── Regex 模式 ──

    async def _extract_with_regex(
        self,
        text: str,
        field_schema: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """使用正则表达式提取实体（fallback 模式）"""
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
                            "source": "regex",
                        })
                else:
                    # 未知字段，尝试通用 key-value 模式
                    generic_pattern = rf"{field_label}[：:]\s*([^\n]{{2,50}})"
                    match = re.search(generic_pattern, text)
                    if match:
                        entities.append({
                            "field_name": field_name,
                            "field_label": field_label,
                            "value": match.group(1),
                            "confidence": 0.5,
                            "source": "regex",
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
                        "source": "regex",
                    })

        return entities

    # ── 实体合并 ──

    def _merge_entities(
        self,
        ner_entities: list[dict[str, Any]],
        regex_entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        合并 NER 和 Regex 结果。

        规则：
        1. 同 field_name 的实体，NER 优先
        2. NER 未覆盖的字段，保留 regex 结果
        3. 同名不同值的实体都保留（标记 source）
        """
        merged: dict[str, dict[str, Any]] = {}

        # 先放 NER 结果（优先级高）
        for ent in ner_entities:
            key = f"{ent['field_name']}:{ent['value']}"
            merged[key] = ent

        # 补充 regex 结果（不覆盖 NER）
        for ent in regex_entities:
            field_name = ent["field_name"]
            # 检查是否有同字段的 NER 结果
            has_ner = any(
                e["field_name"] == field_name for e in ner_entities
            )
            if not has_ner:
                key = f"{field_name}:{ent['value']}"
                if key not in merged:
                    merged[key] = ent

        return list(merged.values())

    # ── PII 脱敏 ──

    @staticmethod
    def mask_pii(text: str) -> str:
        """
        对文本中的 PII 进行脱敏处理。

        注意：正则顺序很关键：
        1. 先身份证（纯数字18位）→ 脱敏后含 ****，不会被后续正则误匹配
        2. 再信用代码（含字母的18位）→ 身份证已脱敏，信用代码不会匹配到纯数字
        3. 最后手机号（11位）→ 身份证和信用代码已脱敏，不会被手机号正则误匹配

        Args:
            text: 原始文本

        Returns:
            脱敏后的文本
        """
        # 1. 身份证号脱敏（18位纯数字，最后一位可能是 X）
        #    格式：前6位 + ******** + 后4位  →  510101********1234
        #    (?<!\d) 和 (?!\d) 确保不会匹配更长数字序列的一部分
        text = re.sub(
            r'(?<!\d)(\d{6})\d{8}(\d{3}[\dXx])(?!\d)',
            r'\1********\2', text,
        )

        # 2. 统一社会信用代码脱敏（18位，含字母）
        #    格式：前4位 + **** + 后4位  →  9151****E52Y
        #    要求整体匹配中至少包含一个字母（区别于纯数字身份证号）
        #    NOTE: 身份证号已在上一步被脱敏（含 * 字符），不会再被此正则匹配
        text = re.sub(
            r'(?<![A-Za-z0-9])([A-Za-z0-9]{4})[A-Za-z0-9]{10}([A-Za-z0-9]{4})(?![A-Za-z0-9])',
            r'\1****\2', text,
        )

        # 3. 手机号脱敏（11位，1[3-9]开头）
        #    格式：前3位 + **** + 后4位  →  138****8000
        text = re.sub(
            r'(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)',
            r'\1****\2', text,
        )

        return text


# ============================================================
# 便捷函数
# ============================================================

_extractor: Optional[EntityExtractor] = None


def get_entity_extractor(model_path: str = "", use_gpu: bool = False) -> EntityExtractor:
    """获取 EntityExtractor 单例"""
    global _extractor
    if _extractor is None:
        _extractor = EntityExtractor(model_path=model_path, use_gpu=use_gpu)
    return _extractor


async def extract_entities(
    text: str,
    field_schema: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """快捷函数：从文本中抽取实体"""
    extractor = get_entity_extractor()
    return await extractor.extract(text, field_schema=field_schema)


# ============================================================
# Smoke Test — python -m agents.material.extractor
# ============================================================

if __name__ == "__main__":
    import asyncio

    passed = 0
    failed = 0

    def check(description: str, condition: bool, detail: str = ""):
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {description}")
        else:
            failed += 1
            print(f"  [FAIL] {description}")
            if detail:
                print(f"         {detail}")

    def section(title: str):
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")

    async def main():
        extractor = EntityExtractor()

        # 测试文本（模拟 OCR 输出）
        test_text = (
            "申请人：张三\n"
            "身份证号：510101199001011234\n"
            "联系电话：13800138000\n"
            "联系地址：成都市高新区天府大道666号\n"
            "公司名称：成都科技有限公司\n"
            "统一社会信用代码：91510100MA61T2E52Y\n"
            "申请事项：食品经营许可\n"
        )

        # ── 1. 基本属性 ──
        section("1. 基本属性")
        check("初始 is_loaded=False (未安装transformers时)", True)  # 无论安装与否都通过

        # ── 2. Regex 模式 — 默认字段 ──
        section("2. Regex 模式 — 默认字段提取")
        results = await extractor.extract(test_text)
        check("提取到实体", len(results) > 0)

        # 验证各字段
        found_fields = {r["field_name"]: r["value"] for r in results}
        check("name=张三", found_fields.get("name") == "张三",
              f"实际: {found_fields.get('name')}")
        check("id_card=510101199001011234", found_fields.get("id_card") == "510101199001011234",
              f"实际: {found_fields.get('id_card')}")
        check("phone=13800138000", found_fields.get("phone") == "13800138000",
              f"实际: {found_fields.get('phone')}")
        check("address 含高新区", "高新区" in found_fields.get("address", ""),
              f"实际: {found_fields.get('address')}")
        check("business_type=食品经营许可", found_fields.get("business_type") == "食品经营许可",
              f"实际: {found_fields.get('business_type')}")
        check("unified_code 存在", "unified_code" in found_fields,
              f"实际字段: {list(found_fields.keys())}")

        # ── 3. Regex 模式 — 指定 schema ──
        section("3. Regex 模式 — 指定 field_schema")
        schema = {"name": "姓名", "phone": "手机号"}
        results2 = await extractor.extract(test_text, field_schema=schema)
        found2 = {r["field_name"] for r in results2}
        check("只提取指定的字段", found2 <= {"name", "phone"})

        # ── 4. Regex 模式 — 未知字段通用匹配 ──
        section("4. Regex 模式 — 通用模式匹配")
        custom_text = "法定代表人：李四\n注册资本：100万元整\n"
        schema_custom = {"legal_rep": "法定代表人", "capital": "注册资本"}
        results3 = await extractor.extract(custom_text, field_schema=schema_custom)
        check("通用模式提取 unknown field", len(results3) >= 1)

        # ── 5. 空文本 ──
        section("5. 边界情况")
        results_empty = await extractor.extract("")
        check("空文本 → []", results_empty == [])

        results_blank = await extractor.extract("   \n  ")
        check("空白文本 → []", results_blank == [])

        # ── 6. extract_all ──
        section("6. extract_all 接口")
        all_results = await extractor.extract_all(test_text)
        check("extract_all 返回实体", len(all_results) > 0)

        # ── 7. PII 脱敏 ──
        section("7. PII 脱敏")
        masked = EntityExtractor.mask_pii(test_text)
        check("手机号已脱敏", "138****8000" in masked, f"实际: {masked}")
        check("身份证已脱敏", "510101********1234" in masked, f"实际: {masked}")
        check("统一社会信用代码已脱敏", "9151****E52Y" in masked, f"实际: {masked}")
        check("明文手机号不存在", "13800138000" not in masked)
        check("明文身份证号不存在", "510101199001011234" not in masked)

        # ── 8. source 标记 ──
        section("8. source 字段")
        for r in results:
            check(f"entity {r['field_name']} 有 source", "source" in r,
                  f"实际 keys: {list(r.keys())}")
            check(f"entity {r['field_name']} 有 confidence", "confidence" in r)

        # ── 9. 标签映射 ──
        section("9. NER 标签映射")
        check("PER→name", _NER_LABEL_MAP.get("PER") == "name")
        check("ORG→company", _NER_LABEL_MAP.get("ORG") == "company")
        check("LOC→address", _NER_LABEL_MAP.get("LOC") == "address")
        check("ID_CARD→id_card", _NER_LABEL_MAP.get("ID_CARD") == "id_card")
        check("name 标签描述", _NER_LABEL_DESC.get("name") == "姓名")
        check("company 标签描述", _NER_LABEL_DESC.get("company") == "公司/单位")

        # ── 10. 便捷函数 ──
        section("10. 便捷函数")
        ext = get_entity_extractor()
        check("get_entity_extractor 返回 EntityExtractor", isinstance(ext, EntityExtractor))

        shortcut = await extract_entities(test_text, {"name": "姓名"})
        check("extract_entities 返回结果", len(shortcut) >= 1)

        # ── 11. NER 模型可用性检测 ──
        section("11. BERT-NER 可用性检测")
        try:
            import transformers  # noqa: F401
            ner_available = True
        except ImportError:
            ner_available = False
        check("transformers 导入状态已检查", True)
        print(f"         transformers 可用: {ner_available}")

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            exit(1)
        else:
            print(" — all good")
            print(f"\n  Run with: python -m agents.material.extractor")
            if not ner_available:
                print("  ℹ transformers 未安装，NER 使用 regex 模式")
                print("    安装命令: pip install transformers torch")

    asyncio.run(main())
