"""
mcp.servers.workflow_server.tools - Workflow MCP Tools: create_case, query_status

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement create_case and query_status tool functions
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from tools.logger import get_logger
from tools.mcp.schema import CreateCaseOutput, QueryStatusOutput

logger = get_logger(__name__)

_MOCK_CASES: dict[str, dict] = {}


async def create_case(
    user_id: str,
    service: str,
    materials: list[str] | None = None,
) -> CreateCaseOutput:
    """
    创建新的政务办件。当前为 stub 实现，Phase 3 接入真实业务 API。
    """
    case_id = f"CASE_{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    logger.info("create_case: case_id={} user={} service={}", case_id, user_id, service)

    _MOCK_CASES[case_id] = {
        "case_id": case_id,
        "user_id": user_id,
        "service": service,
        "materials": materials or [],
        "status": "created",
        "created_at": now,
        "updated_at": now,
    }

    return CreateCaseOutput(
        case_id=case_id,
        status="created",
        service=service,
        user_id=user_id,
        created_at=now,
    )


async def query_status(case_id: str) -> QueryStatusOutput:
    """
    查询办件状态。基于 case_id hash 返回确定性模拟状态。
    """
    logger.info("query_status: case_id={}", case_id)

    now = datetime.now(timezone.utc).isoformat()
    mock_case = _MOCK_CASES.get(case_id)
    if mock_case:
        status = _compute_status(case_id)
        mock_case["status"] = status
        mock_case["updated_at"] = now

    status = _compute_status(case_id)
    return QueryStatusOutput(
        case_id=case_id,
        status=status,
        progress=_status_message(status),
        updated_at=now,
    )


def _compute_status(case_id: str) -> str:
    """基于 case_id 确定性计算状态"""
    hash_val = int(hashlib.md5(case_id.encode()).hexdigest()[:8], 16)
    statuses = ["created", "processing", "reviewing", "completed"]
    if any(kw in case_id for kw in ("CASE_0", "CASE_1")):
        return "created"
    if any(kw in case_id for kw in ("CASE_F", "CASE_E")):
        return "completed"
    return statuses[hash_val % len(statuses)]


def _status_message(status: str) -> str:
    messages = {
        "created": "办件已创建，等待分配处理人员",
        "processing": "办件处理中，正在审核提交材料",
        "reviewing": "材料审核完成，正在进行最终审批",
        "completed": "办件已完成，请留意短信通知领取结果",
    }
    return messages.get(status, f"当前状态: {status}")
