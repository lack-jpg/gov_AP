"""
a2a.mock_agents.housing_agent - Mock external housing/property Agent for A2A testing

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement mock housing agent with query_property skill
"""
from __future__ import annotations

import asyncio
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from tools.logger import get_logger
from tools.a2a.protocol import A2ATaskRequest, A2ATaskResponse, AgentCard, A2ATaskStatus

logger = get_logger(__name__)

# AgentCard 中对外公布的端点（Docker 内可用 A2A_HOUSING_URL 覆盖）
_DEFAULT_ENDPOINT = os.environ.get("A2A_HOUSING_URL", "http://localhost:12201")


# ============================================================
# Mock 数据 — 模拟不动产信息
# ============================================================

_MOCK_PROPERTIES: list[dict[str, Any]] = [
    {
        "property_id": "PROP-CD-20230001",
        "address": "成都市锦江区天府大道168号万科城市花园3栋2单元1501",
        "area_sqm": 128.5,
        "type": "住宅",
        "owner": "张三",
        "owner_id_card": "510103199003071234",
        "registration_date": "2021-06-15",
        "property_right_no": "川(2021)成都市不动产权第0123456号",
        "mortgage_status": "无抵押",
        "estimated_value": 3500000.0,
    },
    {
        "property_id": "PROP-CD-20230002",
        "address": "成都市武侯区科华北路88号力宝大厦12层1201",
        "area_sqm": 85.3,
        "type": "商业",
        "owner": "张三",
        "owner_id_card": "510103199003071234",
        "registration_date": "2022-03-20",
        "property_right_no": "川(2022)成都市不动产权第0789123号",
        "mortgage_status": "抵押中（建设银行）",
        "estimated_value": 1800000.0,
    },
    {
        "property_id": "PROP-CD-20230003",
        "address": "成都市高新区天府软件园C区7栋",
        "area_sqm": 450.0,
        "type": "办公",
        "owner": "李四",
        "owner_id_card": "510104198512150088",
        "registration_date": "2023-01-10",
        "property_right_no": "川(2023)成都市不动产权第0456789号",
        "mortgage_status": "无抵押",
        "estimated_value": 8000000.0,
    },
]

_MOCK_HOUSING_FUND: list[dict[str, Any]] = [
    {
        "owner": "张三",
        "owner_id_card": "510103199003071234",
        "housing_fund_account": "0282023001234",
        "balance": 285600.50,
        "monthly_deposit": 3600.00,
        "unit_ratio": "12%",
        "personal_ratio": "12%",
        "last_deposit_date": "2026-07-25",
        "total_withdrawals": 120000.00,
    },
]


# ============================================================
# HousingAgent — 模拟外部不动产系统 Agent
# ============================================================


class HousingAgent:
    """
    模拟外部不动产系统 Agent。

    提供技能:
    - query_property: 根据 owner_name 或 property_id 查询不动产信息
    - register_property: 模拟不动产登记

    支持两种使用模式:
    1. 直接调用（stub 模式）：agent.query_property(owner_name="张三")
    2. HTTP Server 模式：通过 FastAPI 暴露为独立服务

    用法:
        agent = HousingAgent()
        result = await agent.process_task(task_request)
    """

    def __init__(self):
        self.agent_id = f"housing_agent_{uuid.uuid4().hex[:6]}"
        self.card = AgentCard(
            name="housing_agent",
            display_name="不动产系统Agent",
            description="提供不动产登记查询、产权核验等服务",
            skills=["query_property", "register_property"],
            endpoint=_DEFAULT_ENDPOINT,
            version="0.1.0",
            timeout_ms=15000,
        )

    async def process_task(self, request: A2ATaskRequest) -> A2ATaskResponse:
        """
        处理 A2A 任务请求。

        模拟异步延迟（0.5-1.5s），模拟真实外部系统调用。

        Args:
            request: A2A 任务请求

        Returns:
            A2A 任务响应
        """
        skill = request.skill

        # 模拟网络延迟
        delay = random.uniform(0.3, 1.0)
        await asyncio.sleep(delay)

        try:
            if skill == "query_property":
                artifact = self._query_property(request.input)
                return A2ATaskResponse(
                    task_id=request.task_id,
                    status=A2ATaskStatus.COMPLETED,
                    artifact=artifact,
                    agent_name="housing_agent",
                    duration_ms=delay * 1000,
                )
            elif skill == "register_property":
                artifact = self._register_property(request.input)
                return A2ATaskResponse(
                    task_id=request.task_id,
                    status=A2ATaskStatus.COMPLETED,
                    artifact=artifact,
                    agent_name="housing_agent",
                    duration_ms=delay * 1000,
                )
            else:
                return A2ATaskResponse(
                    task_id=request.task_id,
                    status=A2ATaskStatus.FAILED,
                    error_message=f"Unknown skill: {skill}",
                    agent_name="housing_agent",
                    duration_ms=delay * 1000,
                )
        except Exception as e:
            logger.error("HousingAgent error: {}", e)
            return A2ATaskResponse(
                task_id=request.task_id,
                status=A2ATaskStatus.FAILED,
                error_message=str(e),
                agent_name="housing_agent",
                duration_ms=delay * 1000,
            )

    # ── 技能实现 ──

    def _query_property(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        查询不动产信息。

        支持按 owner_name 或 property_id 查询。
        """
        owner_name = input_data.get("owner_name", "")
        owner_id_card = input_data.get("owner_id_card", "")
        property_id = input_data.get("property_id", "")

        results: list[dict] = []

        for prop in _MOCK_PROPERTIES:
            match = False
            if property_id and prop["property_id"] == property_id:
                match = True
            elif owner_name and prop["owner"] == owner_name:
                match = True
            elif owner_id_card and prop["owner_id_card"] == owner_id_card:
                match = True

            if match:
                # 脱敏后返回
                results.append({
                    "property_id": prop["property_id"],
                    "address": prop["address"],
                    "area_sqm": prop["area_sqm"],
                    "type": prop["type"],
                    "owner": prop["owner"],
                    "registration_date": prop["registration_date"],
                    "mortgage_status": prop["mortgage_status"],
                })

        # 同时返回公积金信息（如果匹配）
        fund_info: list[dict] = []
        for hf in _MOCK_HOUSING_FUND:
            if owner_name and hf["owner"] == owner_name:
                fund_info.append({
                    "account": hf["housing_fund_account"],
                    "balance": hf["balance"],
                    "monthly_deposit": hf["monthly_deposit"],
                })
            elif owner_id_card and hf["owner_id_card"] == owner_id_card:
                fund_info.append({
                    "account": hf["housing_fund_account"],
                    "balance": hf["balance"],
                    "monthly_deposit": hf["monthly_deposit"],
                })

        return {
            "properties": results,
            "total_count": len(results),
            "housing_fund": fund_info,
            "query_time": datetime.now(timezone.utc).isoformat(),
        }

    def _register_property(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        模拟不动产登记。
        """
        return {
            "registration_id": f"REG-{uuid.uuid4().hex[:8].upper()}",
            "status": "accepted",
            "estimated_days": random.randint(5, 15),
            "application_no": f"APP-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }


# ============================================================
# 直接调用（stub 模式）便捷函数
# ============================================================

_agent: Optional[HousingAgent] = None


def get_housing_agent() -> HousingAgent:
    """获取 HousingAgent 单例"""
    global _agent
    if _agent is None:
        _agent = HousingAgent()
    return _agent


async def query_property_stub(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    直接调用 HousingAgent 查询不动产（无需 HTTP/外部服务）。

    用于 stub fallback 模式。
    """
    agent = get_housing_agent()
    task_id = f"a2a_stub_{uuid.uuid4().hex[:8]}"
    request = A2ATaskRequest(
        task_id=task_id,
        skill="query_property",
        input=input_data,
    )
    response = await agent.process_task(request)
    return response.artifact or {}


async def register_property_stub(input_data: dict[str, Any]) -> dict[str, Any]:
    """直接调用 HousingAgent 登记不动产（stub）"""
    agent = get_housing_agent()
    task_id = f"a2a_stub_{uuid.uuid4().hex[:8]}"
    request = A2ATaskRequest(
        task_id=task_id,
        skill="register_property",
        input=input_data,
    )
    response = await agent.process_task(request)
    return response.artifact or {}


# ============================================================
# Smoke Test — python -m tools.a2a.mock_agents.housing_agent
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
        # ── 1. Agent Card ──
        section("1. Agent Card")
        agent = HousingAgent()
        check("agent_id starts with housing_agent_", agent.agent_id.startswith("housing_agent_"))
        check("card.name == housing_agent", agent.card.name == "housing_agent")
        check("skills: query_property", "query_property" in agent.card.skills)
        check("skills: register_property", "register_property" in agent.card.skills)

        # ── 2. query_property — by owner_name ──
        section("2. query_property — by owner_name")
        req = A2ATaskRequest(
            task_id="test_001",
            skill="query_property",
            input={"owner_name": "张三"},
        )
        resp = await agent.process_task(req)
        check("status == completed", resp.status == A2ATaskStatus.COMPLETED)
        check("artifact present", resp.artifact is not None)
        assert resp.artifact is not None
        check("properties found", resp.artifact["total_count"] == 2)
        check("property address", "天府大道" in resp.artifact["properties"][0]["address"])
        check("housing_fund included", len(resp.artifact.get("housing_fund", [])) > 0)
        check("duration_ms > 0", resp.duration_ms > 0)

        # ── 3. query_property — by property_id ──
        section("3. query_property — by property_id")
        req2 = A2ATaskRequest(
            task_id="test_002",
            skill="query_property",
            input={"property_id": "PROP-CD-20230003"},
        )
        resp2 = await agent.process_task(req2)
        assert resp2.artifact is not None
        check("single result", resp2.artifact["total_count"] == 1)
        check("owner is 李四", resp2.artifact["properties"][0]["owner"] == "李四")

        # ── 4. query_property — by id_card ──
        section("4. query_property — by id_card")
        req3 = A2ATaskRequest(
            task_id="test_003",
            skill="query_property",
            input={"owner_id_card": "510103199003071234"},
        )
        resp3 = await agent.process_task(req3)
        assert resp3.artifact is not None
        check("match by id_card", resp3.artifact["total_count"] >= 1)

        # ── 5. query_property — no match ──
        section("5. query_property — no match")
        req4 = A2ATaskRequest(
            task_id="test_004",
            skill="query_property",
            input={"owner_name": "王五"},
        )
        resp4 = await agent.process_task(req4)
        assert resp4.artifact is not None
        check("zero results", resp4.artifact["total_count"] == 0)

        # ── 6. register_property ──
        section("6. register_property")
        req5 = A2ATaskRequest(
            task_id="test_005",
            skill="register_property",
            input={"property_address": "成都市金牛区XX路88号", "owner_name": "张三"},
        )
        resp5 = await agent.process_task(req5)
        check("register completed", resp5.status == A2ATaskStatus.COMPLETED)
        assert resp5.artifact is not None
        check("registration_id", resp5.artifact["registration_id"].startswith("REG-"))
        check("status accepted", resp5.artifact["status"] == "accepted")

        # ── 7. Unknown skill ──
        section("7. Unknown skill")
        req6 = A2ATaskRequest(
            task_id="test_006",
            skill="unknown_skill",
            input={},
        )
        resp6 = await agent.process_task(req6)
        check("unknown skill → failed", resp6.status == A2ATaskStatus.FAILED)
        check("error message set", resp6.error_message is not None)

        # ── 8. Stub 便捷函数 ──
        section("8. Stub 便捷函数")
        result = await query_property_stub({"owner_name": "张三"})
        check("stub query: results", result.get("total_count", 0) >= 1)

        reg_result = await register_property_stub({"owner_name": "张三"})
        check("stub register: status accepted", reg_result.get("status") == "accepted")

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            exit(1)
        else:
            print(" — all good")
            print(f"\n  Run with: python -m tools.a2a.mock_agents.housing_agent")

    asyncio.run(main())
