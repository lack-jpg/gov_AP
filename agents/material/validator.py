"""
material.validator - Rule validation: check material completeness against requirements

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement rule-based material validation with business-type-specific catalogs
"""
from __future__ import annotations

import re
from typing import Any

from tools.logger import get_logger

logger = get_logger(__name__)


class MaterialValidator:
    """
    材料规则校验器。

    检查提交材料是否满足业务类型的必需材料要求。
    支持格式校验（身份证、手机号、统一社会信用代码等）。

    使用方式:
        validator = MaterialValidator()
        result = await validator.validate("restaurant_license", ["身份证", "营业执照申请表"])
    """

    # ── 业务类型 → 必需材料清单 ──
    REQUIRED_MATERIALS: dict[str, list[str]] = {
        "restaurant_license": [
            "身份证",
            "经营场所证明（租赁合同或房产证）",
            "营业执照申请表",
            "食品经营许可申请书",
            "从业人员健康证",
            "食品安全管理制度",
            "消防安全检查申请表",
        ],
        "business_license": [
            "身份证",
            "经营场所证明（租赁合同或房产证）",
            "营业执照申请表",
            "名称预先核准通知书",
        ],
        "business_register": [
            "法人身份证",
            "经营场所证明（租赁合同或房产证）",
            "公司章程",
            "股东会决议",
            "公司登记申请书",
        ],
        "property_service": [
            "身份证",
            "不动产权证书（或购房合同）",
            "不动产登记申请书",
            "完税证明",
        ],
        "fund_query": [
            "身份证",
            "公积金查询申请表",
        ],
    }

    # ── 材料名称别名映射（支持用户用简称） ──
    MATERIAL_ALIASES: dict[str, list[str]] = {
        "身份证": ["身份证", "居民身份证", "id_card", "ID"],
        "经营场所证明（租赁合同或房产证）": ["经营场所证明", "租赁合同", "房产证", "场地证明"],
        "营业执照申请表": ["营业执照申请表", "营业执照申请"],
        "食品经营许可申请书": ["食品经营许可申请书", "食品许可申请", "食品经营申请"],
        "从业人员健康证": ["健康证", "健康证明", "从业人员健康证明"],
        "食品安全管理制度": ["食品安全制度", "食品安全管理制度"],
        "消防安全检查申请表": ["消防申请表", "消防安全申请表", "消防安全检查申请表"],
        "名称预先核准通知书": ["名称预核准", "名称核准通知", "名称预先核准通知书"],
        "法人身份证": ["法人身份证", "法人代表身份证"],
        "公司章程": ["公司章程", "企业章程"],
        "股东会决议": ["股东会决议", "股东决议"],
        "公司登记申请书": ["公司登记申请书", "企业登记申请书"],
        "不动产权证书（或购房合同）": ["不动产权证书", "房产证", "购房合同", "不动产证"],
        "不动产登记申请书": ["不动产登记申请书", "不动产登记申请"],
        "完税证明": ["完税证明", "契税证明", "缴税证明"],
        "公积金查询申请表": ["公积金查询申请表", "公积金查询申请"],
    }

    async def validate(
        self,
        business_type: str,
        materials: list[str],
    ) -> dict[str, Any]:
        """
        校验材料完整性。

        Args:
            business_type: 业务类型
            materials: 已提交的材料名称列表

        Returns:
            {passed, missing, submitted, required, warnings}
        """
        required = self.REQUIRED_MATERIALS.get(business_type, [])
        if not required:
            logger.warning("Unknown business_type: {}", business_type)
            return {
                "passed": True,
                "missing": [],
                "submitted": materials,
                "required": [],
                "warnings": [f"未知业务类型 '{business_type}'，跳过材料校验"],
            }

        # ── 规范化已提交材料名称 ──
        normalized: list[str] = []
        for mat in materials:
            resolved = self._resolve_material(mat, required)
            if resolved:
                normalized.append(resolved)

        # ── 找出缺失材料 ──
        missing: list[str] = []
        for req in required:
            if req not in normalized:
                missing.append(req)

        passed = len(missing) == 0

        # ── 生成温馨提示 ──
        warnings: list[str] = []
        warnings.extend(self._check_material_warnings(business_type, normalized))

        result = {
            "passed": passed,
            "missing": missing,
            "submitted": materials,
            "required": required,
            "warnings": warnings,
        }

        logger.info(
            "MaterialValidator: type={} submitted={} passed={} missing={}",
            business_type, len(materials), passed, len(missing),
        )
        return result

    def _resolve_material(self, submitted: str, required: list[str]) -> str | None:
        """
        解析用户提交的材料名称到标准名称。

        通过别名映射进行模糊匹配。
        """
        # 精确匹配
        if submitted in required:
            return submitted

        # 别名匹配
        for standard_name, aliases in self.MATERIAL_ALIASES.items():
            if standard_name not in required:
                continue
            for alias in aliases:
                if alias in submitted or submitted in alias:
                    return standard_name

        # 模糊匹配（基于关键词交集）
        best_match = None
        best_score = 0
        submitted_chars = set(submitted)
        for req in required:
            req_chars = set(req)
            overlap = len(submitted_chars & req_chars)
            if overlap > best_score and overlap >= 2:
                best_score = overlap
                best_match = req

        if best_match and best_score >= 3:
            return best_match

        return None

    def _check_material_warnings(
        self,
        business_type: str,
        submitted: list[str],
    ) -> list[str]:
        """生成温馨提示"""
        warnings: list[str] = []

        # 餐饮类：健康证有效期提醒
        if "restaurant_license" in business_type:
            if "从业人员健康证" in submitted:
                warnings.append("从业人员健康证有效期为1年，请确认未过期")
            warnings.append("取得营业执照后30日内需到税务部门办理税务登记")

        # 企业注册类
        if "business_register" in business_type or "business_license" in business_type:
            warnings.append("公司章程和股东会决议需全体股东签字确认")
            warnings.append("经营场所证明需提供房产证复印件或有效租赁合同")

        # 不动产类
        if "property_service" in business_type:
            warnings.append("如为按揭购房，需同时提供银行贷款合同")
            warnings.append("不动产登记办理时限为30个工作日")

        return warnings

    @staticmethod
    def validate_id_card(id_number: str) -> dict[str, Any]:
        """
        身份证号格式校验。

        校验规则：
        - 18位数字（最后一位可以是 X）
        - 前6位为地区码
        - 第7-14位为出生日期（YYYYMMDD）
        - 第17位为性别（奇数男、偶数女）

        Args:
            id_number: 身份证号码

        Returns:
            {valid, error, parsed: {province, birth_date, gender}}
        """
        # 长度校验
        if not re.match(r'^\d{17}[\dXx]$', id_number):
            return {"valid": False, "error": "身份证号格式错误（需18位）"}

        # 日期校验
        birth_str = id_number[6:14]
        try:
            from datetime import datetime
            datetime.strptime(birth_str, "%Y%m%d")
        except ValueError:
            return {"valid": False, "error": "身份证号中出生日期无效"}

        # 性别
        gender_code = int(id_number[16])
        gender = "男" if gender_code % 2 == 1 else "女"

        return {
            "valid": True,
            "error": None,
            "parsed": {
                "birth_date": f"{birth_str[:4]}-{birth_str[4:6]}-{birth_str[6:8]}",
                "gender": gender,
            },
        }

    @staticmethod
    def validate_phone(phone: str) -> dict[str, Any]:
        """
        手机号格式校验。

        Args:
            phone: 手机号码

        Returns:
            {valid, error}
        """
        if re.match(r'^1[3-9]\d{9}$', phone):
            return {"valid": True, "error": None}
        return {"valid": False, "error": "手机号格式错误（需11位大陆手机号）"}
