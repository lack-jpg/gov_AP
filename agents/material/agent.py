"""
material.agent - Material Agent core: material completeness and validity review

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement Material Agent with OCR + entity extraction + rule validation
"""
from __future__ import annotations

from typing import Any, Optional

from langchain_core.language_models import BaseChatModel

from orchestration.langgraph.state import AgentState, MaterialCheckResult
from tools.logger import get_logger

logger = get_logger(__name__)


class MaterialAgent:
    """
    Material Agent — 材料审核。

    流程: 文档上传 → OCR 识别 → 实体/字段抽取 → 规则校验 → 审核结果

    当前实现: 基于预定义规则的检查（OCR 待接入）
    TODO: 接入 OCR 引擎 + 实体抽取模型

    使用方式:
        agent = MaterialAgent(llm=llm)
        result = await agent.review(file_bytes, business_type)

    LangGraph 集成:
        result = await agent.review(None, state["intent"])
        state["material_result"] = result.model_dump()
    """

    # 各业务类型的必需材料清单
    REQUIRED_MATERIALS: dict[str, list[str]] = {
        "restaurant_license": [
            "身份证明",
            "经营场所证明",
            "食品安全管理制度",
            "从业人员健康证",
            "食品经营设备清单",
        ],
        "business_license": [
            "身份证明",
            "经营场所证明",
            "名称预先核准通知书",
        ],
        "business_register": [
            "法人身份证明",
            "经营场所证明",
            "公司章程",
            "股东会决议",
            "验资报告",
        ],
        "property_service": [
            "身份证明",
            "购房合同",
            "完税证明",
            "房屋测绘报告",
        ],
        "fund_query": [
            "身份证明",
        ],
    }

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._llm = llm

    async def review(
        self,
        file_bytes: Optional[bytes] = None,
        business_type: str = "business_license",
        submitted_materials: Optional[list[str]] = None,
    ) -> MaterialCheckResult:
        """
        审核材料完整性和合规性。

        Args:
            file_bytes: 上传的文件内容（TODO: OCR）
            business_type: 业务类型
            submitted_materials: 用户声称已提交的材料列表

        Returns:
            MaterialCheckResult
        """
        # 获取必需材料清单
        required = self.REQUIRED_MATERIALS.get(business_type, ["身份证明"])

        # TODO: OCR + 实体抽取
        # if file_bytes:
        #     text = await self._ocr_engine.extract_text(file_bytes)
        #     extracted = await self._extractor.extract(text, schema)

        # 规则校验
        if submitted_materials:
            missing = [m for m in required if m not in submitted_materials]
            warnings = self._check_warnings(submitted_materials)
        else:
            # 无材料列表 → 提示所有需要的材料
            missing = required
            warnings = ["未检测到已提交材料，请上传相关文件进行审核"]

        passed = len(missing) == 0

        return MaterialCheckResult(
            passed=passed,
            missing=missing,
            warnings=warnings,
            extracted_fields={},
        )

    async def process(self, state: AgentState) -> AgentState:
        """
        LangGraph 节点接口。

        Args:
            state: 当前 AgentState

        Returns:
            更新后的 AgentState
        """
        intent = state.get("intent", "business_license")
        result = await self.review(file_bytes=None, business_type=intent)
        state["material_result"] = result.model_dump()
        return state

    def _check_warnings(self, materials: list[str]) -> list[str]:
        """检查材料的潜在问题"""
        warnings: list[str] = []
        mat_str = " ".join(materials).lower()

        if "身份证" in mat_str or "身份证明" in mat_str:
            warnings.append("请确保身份证在有效期内且照片清晰")
        if "经营场所" in mat_str:
            warnings.append("经营场所证明需包含有效的租赁合同或房产证")
        if "健康证" in mat_str:
            warnings.append("健康证有效期通常为1年，请确认未过期")

        return warnings
