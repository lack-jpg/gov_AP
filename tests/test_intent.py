"""
test_intent - Intent classification tests
"""
from __future__ import annotations

import pytest

from agents.intent.classifier import IntentClassifier
from agents.intent.schema import INTENT_LABELS


class TestIntentClassifier:
    def setup_method(self):
        self.classifier = IntentClassifier()

    @pytest.mark.asyncio
    async def test_restaurant(self):
        result = await self.classifier.classify("我想开一家餐馆")
        assert result.label == "restaurant_license"

    @pytest.mark.asyncio
    async def test_fund_query(self):
        result = await self.classifier.classify("查询公积金余额")
        assert result.label == "fund_query"

    @pytest.mark.asyncio
    async def test_property(self):
        result = await self.classifier.classify("办理房产过户")
        assert result.label == "property_service"

    @pytest.mark.asyncio
    async def test_unknown(self):
        result = await self.classifier.classify("今天天气怎么样")
        # 应返回某个合法标签或 unknown
        assert result.label in [lbl.label_id for lbl in INTENT_LABELS] + ["unknown"]

    @pytest.mark.asyncio
    async def test_confidence_in_range(self):
        result = await self.classifier.classify("我想开餐饮店")
        assert 0.0 <= result.confidence <= 1.0


class TestIntentLabels:
    def test_required_labels(self):
        label_ids = {lbl.label_id for lbl in INTENT_LABELS}
        assert "restaurant_license" in label_ids
        assert "business_license" in label_ids
        assert "fund_query" in label_ids
        assert "property_service" in label_ids
