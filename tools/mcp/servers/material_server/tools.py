"""
mcp.servers.material_server.tools - Material MCP Tools: extract_entity, check_material

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement extract_entity and check_material tool functions
"""
from __future__ import annotations

from tools.logger import get_logger
from tools.mcp.schema import (
    ExtractEntityOutput,
    ExtractedEntity,
    CheckMaterialOutput,
)

logger = get_logger(__name__)


# ============================================================
# extract_entity
# ============================================================


async def extract_entity(file_id: str, field_schema: dict[str, str] | None = None) -> ExtractEntityOutput:
    """
    从材料文件中抽取结构化字段信息。

    当前为 stub 实现：使用正则表达式提取。
    Phase 3 接入真实 OCR + NER 模型。

    Args:
        file_id: 文件唯一标识
        field_schema: 需要提取的字段定义

    Returns:
        ExtractEntityOutput
    """
    logger.info("extract_entity called: file_id={}", file_id)

    from agents.material.ocr import OCREngine
    from agents.material.extractor import EntityExtractor

    # ── Stub: OCR → 实体抽取 ──
    engine = OCREngine()
    extractor = EntityExtractor()

    # 模拟文件内容（Phase 3 从文件存储读取）
    mock_bytes = file_id.encode('utf-8') if file_id else b"mock_document"
    text = await engine.extract_text(mock_bytes)

    # 实体抽取
    entities_raw = await extractor.extract(text, field_schema)
    entities = [
        ExtractedEntity(
            field_name=e["field_name"],
            field_label=e["field_label"],
            value=e["value"],
            confidence=e["confidence"],
        )
        for e in entities_raw
    ]

    return ExtractEntityOutput(
        file_id=file_id,
        entities=entities,
        raw_text_preview=text[:200],
    )


# ============================================================
# check_material
# ============================================================


async def check_material(business_type: str, materials: list[str]) -> CheckMaterialOutput:
    """
    检查材料完整性。

    根据业务类型判断已提交材料是否满足要求。

    Args:
        business_type: 业务类型
        materials: 已提交材料名称列表

    Returns:
        CheckMaterialOutput
    """
    logger.info("check_material called: type={} materials={}", business_type, materials)

    from agents.material.validator import MaterialValidator

    validator = MaterialValidator()
    result = await validator.validate(business_type, materials)

    return CheckMaterialOutput(
        passed=result["passed"],
        missing=result.get("missing", []),
        submitted=result.get("submitted", []),
        required=result.get("required", []),
        warnings=result.get("warnings", []),
    )
