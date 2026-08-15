"""
mcp.servers.workflow_server.tools - Workflow MCP Tools: create_case, query_status

Author: le
Date: 2026/7/30
Version: 0.3
Task: Implement create_case and query_status backed by PostgreSQL (P1-5 办件业务落库)

P1-5 变更：
- create_case / query_status 改为经 database.case_service 落库，替代进程内 _MOCK_CASES；
- 办件归属校验沿用 P0-4/P0-5 用户身份：查询办件时校验调用者 user_id（admin 可跨用户）；
- DB 不可用时明确失败（禁止静默 mock）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from tools.logger import get_logger
from tools.mcp.schema import CreateCaseOutput, QueryStatusOutput

logger = get_logger(__name__)


class CaseNotFoundError(Exception):
    """办件不存在或无权限访问（统一提示，避免泄露存在性）。"""


class CallerIdentityRequiredError(Exception):
    """MCP 调用缺少调用者身份（必须经 Gateway 转发身份头）。"""


def _caller_from_headers(headers: dict[str, str]) -> Optional[dict[str, str]]:
    """
    从请求头提取 Gateway 转发的调用者身份。

    Args:
        headers: 请求头（X-User-Id / X-Role / X-Tenant-Id）

    Returns:
        {"user_id": str, "role": str, "tenant_id": str}；身份头缺失时返回 None
    """
    user_id = (headers.get("X-User-Id") or headers.get("x-user-id") or "").strip()
    if not user_id:
        return None
    return {
        "user_id": user_id,
        "role": (headers.get("X-Role") or headers.get("x-role") or "user").strip(),
        "tenant_id": (headers.get("X-Tenant-Id") or headers.get("x-tenant-id") or "default").strip(),
    }


async def create_case(
    user_id: str,
    service: str,
    materials: Optional[list[str]] = None,
    tenant_id: str = "",
    trace_id: str = "",
    caller: Optional[dict[str, str]] = None,
) -> CreateCaseOutput:
    """
    创建新的政务办件（落 PostgreSQL，重启后仍在）。

    Args:
        user_id: 办件归属用户 ID
        service: 服务类型（对应 intent 标签）
        materials: 已提交材料列表
        tenant_id: 租户 ID（缺省取 caller.tenant_id）
        trace_id: 链路追踪 ID（透传，供审计关联）
        caller: 调用者身份 {user_id, role, tenant_id}（Gateway 转发，用于归属校验）

    Returns:
        CreateCaseOutput

    Raises:
        CallerIdentityRequiredError: 缺少调用者身份（绕过 Gateway 的调用路径）
        PermissionError: 调用者与办件归属用户不一致
        RuntimeError: DB 不可用（明确失败，禁止静默 mock）
    """
    if not caller:
        raise CallerIdentityRequiredError(
            "create_case 需要调用者身份，MCP 调用必须经过 Gateway 转发身份头"
        )
    if caller["user_id"] != user_id:
        raise PermissionError(
            f"办件归属冲突: 调用者 {caller['user_id']} 不能为他人创建办件 (user_id={user_id})"
        )

    logger.info(
        "create_case: case_user={} service={} caller={} trace={}",
        user_id, service, caller["user_id"], trace_id or "-",
    )

    # 通过 DB 落库（P1-5 替代 _MOCK_CASES）
    from database import case_service

    tenant = tenant_id or caller.get("tenant_id", "default")
    case = await case_service.create_case(
        user_id=user_id,
        service=service,
        materials=materials,
        tenant_id=tenant,
        trace_id=trace_id,
    )
    if case is None:
        raise RuntimeError(
            "办件落库失败：数据库不可用或写入失败（已拒绝生成模拟办件）"
        )

    return CreateCaseOutput(
        case_id=case["case_id"],
        status=case["status"],
        service=case["service"],
        user_id=case["user_id"],
        created_at=case["created_at"],
    )


async def query_status(
    case_id: str,
    caller: Optional[dict[str, str]] = None,
) -> QueryStatusOutput:
    """
    查询办件状态（同一数据源）。

    Args:
        case_id: 办件编号
        caller: 调用者身份 {user_id, role, tenant_id}（Gateway 转发，用于归属校验）

    Returns:
        QueryStatusOutput

    Raises:
        CallerIdentityRequiredError: 缺少调用者身份
        CaseNotFoundError: 办件不存在或非本人办件（统一提示）
        RuntimeError: DB 不可用
    """
    if not caller:
        raise CallerIdentityRequiredError(
            "query_status 需要调用者身份，MCP 调用必须经过 Gateway 转发身份头"
        )

    logger.info("query_status: case_id={} caller={}", case_id, caller["user_id"])

    from database import case_service

    case = await case_service.get_case(
        case_id,
        user_id=caller["user_id"],
        role=caller["role"],
    )
    if case is None:
        # 不存在与越权同样返回此提示，避免泄露办件存在性
        raise CaseNotFoundError(
            f"办件 {case_id} 不存在或无权访问"
        )

    now = datetime.now(timezone.utc).isoformat()
    return QueryStatusOutput(
        case_id=case["case_id"],
        status=case["status"],
        progress=case["progress"],
        updated_at=case["updated_at"] or now,
    )


async def list_user_cases(
    caller: Optional[dict[str, str]] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """列出调用者最近的办件（供前端/审计使用）。"""
    if not caller:
        raise CallerIdentityRequiredError(
            "list_user_cases 需要调用者身份，MCP 调用必须经过 Gateway 转发身份头"
        )
    from database import case_service
    return await case_service.list_cases(user_id=caller["user_id"], limit=limit)
