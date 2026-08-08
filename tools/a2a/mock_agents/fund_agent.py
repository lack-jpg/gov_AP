"""
a2a.mock_agents.fund_agent - Mock external fund/provident fund Agent for A2A testing

Author: le
Date: 2026/7/29
Version: 0.2
Task: Implement mock fund agent with query_fund skill
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

# AgentCard 中对外公布的端点（Docker 内可用 A2A_FUND_URL 覆盖）
_DEFAULT_ENDPOINT = os.environ.get("A2A_FUND_URL", "http://localhost:12111")


# ============================================================
# Mock 数据 — 模拟公积金信息
# ============================================================

_MOCK_FUND_DATA: list[dict[str, Any]] = [
    {
        "user_id": "001",
        "user_name": "张三",
        "id_card": "510103199003071234",
        "account_no": "GJJ-0282023001234",
        "balance": 285600.50,
        "monthly_deposit": 3600.00,
        "unit_name": "成都科技有限公司",
        "unit_ratio": 0.12,
        "personal_ratio": 0.12,
        "account_status": "正常",
        "open_date": "2018-07-01",
        "last_deposit_date": "2026-07-25",
        "total_deposit": 342000.00,
        "total_withdrawals": 120000.00,
        "withdrawal_records": [
            {
                "date": "2024-03-15",
                "amount": 80000.00,
                "reason": "购房提取",
                "status": "已到账",
            },
            {
                "date": "2022-09-01",
                "amount": 40000.00,
                "reason": "租房提取",
                "status": "已到账",
            },
        ],
    },
    {
        "user_id": "002",
        "user_name": "李四",
        "id_card": "510104198512150088",
        "account_no": "GJJ-0282023005678",
        "balance": 452300.75,
        "monthly_deposit": 5200.00,
        "unit_name": "成都市规划设计研究院",
        "unit_ratio": 0.12,
        "personal_ratio": 0.12,
        "account_status": "正常",
        "open_date": "2010-03-01",
        "last_deposit_date": "2026-07-25",
        "total_deposit": 780000.00,
        "total_withdrawals": 0.00,
        "withdrawal_records": [],
    },
    {
        "user_id": "003",
        "user_name": "王五",
        "id_card": "510107197801010055",
        "account_no": "GJJ-0282023009999",
        "balance": 156800.00,
        "monthly_deposit": 2400.00,
        "unit_name": "成都市民政局",
        "unit_ratio": 0.12,
        "personal_ratio": 0.12,
        "account_status": "封存",
        "open_date": "2005-01-01",
        "last_deposit_date": "2025-06-30",
        "total_deposit": 620000.00,
        "total_withdrawals": 0.00,
        "withdrawal_records": [],
    },
]

# 公积金贷款计算器数据
_LOAN_LIMITS = {
    "单人最高贷款额度": 400000.00,
    "双人最高贷款额度": 700000.00,
    "最长贷款年限": 30,
}


# ============================================================
# FundAgent — 模拟外部公积金系统 Agent
# ============================================================


class FundAgent:
    """
    模拟外部公积金系统 Agent。

    提供技能:
    - query_fund: 查询公积金余额和缴存明细
    - query_fund_detail: 查询提取记录和贷款额度

    支持两种使用模式:
    1. 直接调用（stub 模式）：agent.query_fund(user_id="001")
    2. HTTP Server 模式：通过 FastAPI 暴露为独立服务

    用法:
        agent = FundAgent()
        result = await agent.process_task(task_request)
    """

    def __init__(self):
        self.agent_id = f"fund_agent_{uuid.uuid4().hex[:6]}"
        self.card = AgentCard(
            name="fund_agent",
            display_name="公积金系统Agent",
            description="提供公积金余额查询、提取记录查询、贷款额度测算等服务",
            skills=["query_fund", "query_fund_detail"],
            endpoint=_DEFAULT_ENDPOINT,
            version="0.1.0",
            timeout_ms=10000,
        )

    async def process_task(self, request: A2ATaskRequest) -> A2ATaskResponse:
        """
        处理 A2A 任务请求。

        模拟异步延迟（0.3-0.8s），模拟真实外部系统调用。

        Args:
            request: A2A 任务请求

        Returns:
            A2A 任务响应
        """
        skill = request.skill

        # 模拟网络延迟
        delay = random.uniform(0.2, 0.7)
        await asyncio.sleep(delay)

        try:
            if skill == "query_fund":
                artifact = self._query_fund(request.input)
                return A2ATaskResponse(
                    task_id=request.task_id,
                    status=A2ATaskStatus.COMPLETED,
                    artifact=artifact,
                    agent_name="fund_agent",
                    duration_ms=delay * 1000,
                )
            elif skill == "query_fund_detail":
                artifact = self._query_fund_detail(request.input)
                return A2ATaskResponse(
                    task_id=request.task_id,
                    status=A2ATaskStatus.COMPLETED,
                    artifact=artifact,
                    agent_name="fund_agent",
                    duration_ms=delay * 1000,
                )
            else:
                return A2ATaskResponse(
                    task_id=request.task_id,
                    status=A2ATaskStatus.FAILED,
                    error_message=f"Unknown skill: {skill}",
                    agent_name="fund_agent",
                    duration_ms=delay * 1000,
                )
        except Exception as e:
            logger.error("FundAgent error: {}", e)
            return A2ATaskResponse(
                task_id=request.task_id,
                status=A2ATaskStatus.FAILED,
                error_message=str(e),
                agent_name="fund_agent",
                duration_ms=delay * 1000,
            )

    # ── 技能实现 ──

    def _query_fund(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        查询公积金基本信息。

        支持按 user_id、user_name 或 id_card 查询。
        """
        user_id = input_data.get("user_id", "")
        user_name = input_data.get("user_name", "")
        id_card = input_data.get("id_card", "")

        results: list[dict] = []

        for fund in _MOCK_FUND_DATA:
            match = False
            if user_id and fund["user_id"] == user_id:
                match = True
            elif user_name and fund["user_name"] == user_name:
                match = True
            elif id_card and fund["id_card"] == id_card:
                match = True

            if match:
                # 脱敏后返回
                results.append({
                    "user_name": fund["user_name"],
                    "account_no": fund["account_no"],
                    "balance": fund["balance"],
                    "monthly_deposit": fund["monthly_deposit"],
                    "unit_name": fund["unit_name"],
                    "unit_ratio": f"{fund['unit_ratio']:.0%}",
                    "personal_ratio": f"{fund['personal_ratio']:.0%}",
                    "account_status": fund["account_status"],
                    "last_deposit_date": fund["last_deposit_date"],
                })

        return {
            "fund_accounts": results,
            "total_count": len(results),
            "loan_limits": _LOAN_LIMITS,
            "query_time": datetime.now(timezone.utc).isoformat(),
        }

    def _query_fund_detail(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        查询公积金详细信息 — 含提取记录和贷款测算。
        """
        user_id = input_data.get("user_id", "")
        user_name = input_data.get("user_name", "")

        results: list[dict] = []

        for fund in _MOCK_FUND_DATA:
            match = False
            if user_id and fund["user_id"] == user_id:
                match = True
            elif user_name and fund["user_name"] == user_name:
                match = True

            if match:
                results.append({
                    "user_name": fund["user_name"],
                    "account_no": fund["account_no"],
                    "balance": fund["balance"],
                    "total_deposit": fund["total_deposit"],
                    "total_withdrawals": fund["total_withdrawals"],
                    "withdrawal_records": fund["withdrawal_records"],
                    "account_status": fund["account_status"],
                    "open_date": fund["open_date"],
                })

        # 贷款额度测算
        max_loan = _LOAN_LIMITS["单人最高贷款额度"] if len(results) <= 1 else _LOAN_LIMITS["双人最高贷款额度"]

        return {
            "fund_details": results,
            "total_count": len(results),
            "max_loan_amount": max_loan,
            "max_loan_years": _LOAN_LIMITS["最长贷款年限"],
            "loan_limits": _LOAN_LIMITS,
            "query_time": datetime.now(timezone.utc).isoformat(),
        }


# ============================================================
# 直接调用（stub 模式）便捷函数
# ============================================================

_agent: Optional[FundAgent] = None


def get_fund_agent() -> FundAgent:
    """获取 FundAgent 单例"""
    global _agent
    if _agent is None:
        _agent = FundAgent()
    return _agent


async def query_fund_stub(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    直接调用 FundAgent 查询公积金（无需 HTTP/外部服务）。

    用于 stub fallback 模式。
    """
    agent = get_fund_agent()
    task_id = f"a2a_stub_{uuid.uuid4().hex[:8]}"
    request = A2ATaskRequest(
        task_id=task_id,
        skill="query_fund",
        input=input_data,
    )
    response = await agent.process_task(request)
    return response.artifact or {}


async def query_fund_detail_stub(input_data: dict[str, Any]) -> dict[str, Any]:
    """直接调用 FundAgent 查询公积金详情（stub）"""
    agent = get_fund_agent()
    task_id = f"a2a_stub_{uuid.uuid4().hex[:8]}"
    request = A2ATaskRequest(
        task_id=task_id,
        skill="query_fund_detail",
        input=input_data,
    )
    response = await agent.process_task(request)
    return response.artifact or {}


# ============================================================
# Smoke Test — python -m tools.a2a.mock_agents.fund_agent
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
        agent = FundAgent()
        check("agent_id starts with fund_agent_", agent.agent_id.startswith("fund_agent_"))
        check("card.name == fund_agent", agent.card.name == "fund_agent")
        check("skills: query_fund", "query_fund" in agent.card.skills)
        check("skills: query_fund_detail", "query_fund_detail" in agent.card.skills)

        # ── 2. query_fund — by user_id ──
        section("2. query_fund — by user_id")
        req = A2ATaskRequest(
            task_id="test_f001",
            skill="query_fund",
            input={"user_id": "001"},
        )
        resp = await agent.process_task(req)
        check("status == completed", resp.status == A2ATaskStatus.COMPLETED)
        check("artifact present", resp.artifact is not None)
        assert resp.artifact is not None
        check("account found", resp.artifact["total_count"] == 1)
        check("balance > 0", resp.artifact["fund_accounts"][0]["balance"] > 0)
        check("unit_name present", resp.artifact["fund_accounts"][0]["unit_name"] == "成都科技有限公司")
        check("loan_limits included", "最长贷款年限" in resp.artifact["loan_limits"])

        # ── 3. query_fund — by user_name ──
        section("3. query_fund — by user_name")
        req2 = A2ATaskRequest(
            task_id="test_f002",
            skill="query_fund",
            input={"user_name": "李四"},
        )
        resp2 = await agent.process_task(req2)
        assert resp2.artifact is not None
        check("李四 found", resp2.artifact["total_count"] == 1)
        check("李四 balance", resp2.artifact["fund_accounts"][0]["balance"] == 452300.75)

        # ── 4. query_fund — no match ──
        section("4. query_fund — no match")
        req3 = A2ATaskRequest(
            task_id="test_f003",
            skill="query_fund",
            input={"user_name": "不存在的用户"},
        )
        resp3 = await agent.process_task(req3)
        assert resp3.artifact is not None
        check("no match", resp3.artifact["total_count"] == 0)

        # ── 5. query_fund_detail ──
        section("5. query_fund_detail")
        req4 = A2ATaskRequest(
            task_id="test_f004",
            skill="query_fund_detail",
            input={"user_id": "001"},
        )
        resp4 = await agent.process_task(req4)
        check("detail completed", resp4.status == A2ATaskStatus.COMPLETED)
        assert resp4.artifact is not None
        check("withdrawal_records included",
              len(resp4.artifact["fund_details"][0]["withdrawal_records"]) == 2)
        check("max_loan_amount", resp4.artifact["max_loan_amount"] == 400000.00)

        # ── 6. query_fund_detail — 封存账户 ──
        section("6. query_fund_detail — 封存账户")
        req5 = A2ATaskRequest(
            task_id="test_f005",
            skill="query_fund_detail",
            input={"user_id": "003"},
        )
        resp5 = await agent.process_task(req5)
        assert resp5.artifact is not None
        check("封存状态",
              resp5.artifact["fund_details"][0]["account_status"] == "封存")

        # ── 7. Stub 便捷函数 ──
        section("7. Stub 便捷函数")
        result = await query_fund_stub({"user_id": "001"})
        check("stub query_fund: account found", result.get("total_count", 0) >= 1)

        detail = await query_fund_detail_stub({"user_id": "002"})
        check("stub query_fund_detail: no withdrawals",
              len(detail.get("fund_details", [{}])[0].get("withdrawal_records", [])) == 0)

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            exit(1)
        else:
            print(" — all good")
            print("\n  Run with: python -m tools.a2a.mock_agents.fund_agent")

    asyncio.run(main())
