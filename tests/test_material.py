"""
test_material - Material Agent review tests
"""
from __future__ import annotations

import pytest

from agents.material.agent import MaterialAgent


class TestMaterialAgent:
    def setup_method(self):
        self.agent = MaterialAgent()

    @pytest.mark.asyncio
    async def test_no_materials_missing_all(self):
        result = await self.agent.review(business_type="restaurant_license", submitted_materials=None)
        assert result.passed is False
        assert len(result.missing) > 0

    @pytest.mark.asyncio
    async def test_complete_materials(self):
        result = await self.agent.review(
            business_type="fund_query",
            submitted_materials=["身份证明", "公积金查询申请表"],
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_partial_materials(self):
        result = await self.agent.review(
            business_type="restaurant_license",
            submitted_materials=["身份证明"],
        )
        assert result.passed is False
        assert len(result.missing) > 0

    @pytest.mark.asyncio
    async def test_alias_resolution(self):
        """身份证明 应被解析为 身份证 别名"""
        result = await self.agent.review(
            business_type="fund_query",
            submitted_materials=["身份证明", "公积金查询申请表"],
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_unknown_business_type(self):
        result = await self.agent.review(business_type="nonexistent_type", submitted_materials=[])
        # 未知类型: validator 设计为跳过校验并给出警告（不硬阻塞）
        assert result.passed is True
        assert len(result.warnings) > 0
