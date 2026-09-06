"""
database.case_service - 政务办件持久化（P1-5 办件业务落库）

workflow_server 经此模块创建/查询办件，替代进程内 _MOCK_CASES。
创建后落 PostgreSQL，重启后仍在；查询时校验用户归属。

遵循仓库 DB 模式：函数内懒导入 get_session_factory + ORM，
DB 不可用时返回 None / 空列表（由调用方决定明确失败，禁止静默 mock）。
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from tools.logger import get_logger

logger = get_logger(__name__)


def new_case_id() -> str:
    """生成办件编号: CASE_XXXXXXXX。"""
    return f"CASE_{uuid.uuid4().hex[:8].upper()}"


def _to_dict(row: Any) -> dict[str, Any]:
    """ORM 对象 → 字典（供工具层序列化）。"""
    return {
        "case_id": row.case_id,
        "user_id": row.user_id,
        "tenant_id": row.tenant_id,
        "service": row.service,
        "materials": row.materials or [],
        "status": row.status,
        "progress": row.progress,
        "error_message": row.error_message,
        "trace_id": row.trace_id,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


# ============================================================
# 办件 CRUD
# ============================================================


async def create_case(
    user_id: str,
    service: str,
    materials: Optional[list[str]] = None,
    tenant_id: str = "",
    trace_id: str = "",
) -> Optional[dict[str, Any]]:
    """
    创建办件并落库。

    Args:
        user_id: 办件归属用户 ID
        service: 服务类型（intent 标签）
        materials: 已提交材料列表
        tenant_id: 租户 ID
        trace_id: 链路追踪 ID

    Returns:
        办件字典；DB 不可用/写入失败返回 None（调用方应明确失败，禁止静默 mock）
    """
    cid = new_case_id()
    try:
        from datetime import datetime, timezone

        from database.connection import get_session_factory
        from database.models import Case

        session_factory = get_session_factory()
        now = datetime.now(timezone.utc)
        async with session_factory() as session:
            case = Case(
                case_id=cid,
                user_id=user_id,
                tenant_id=tenant_id or "default",
                service=service,
                materials=materials or [],
                status="created",
                progress="办件已创建，等待分配处理人员",
                trace_id=trace_id or "",
                created_at=now,
                updated_at=now,
            )
            session.add(case)
            await session.commit()
        logger.info("办件创建落库: {} user={} service={} trace={}", cid, user_id, service, trace_id or "-")
        return _to_dict(case)
    except Exception as e:
        logger.error("办件落库失败（不生成模拟数据）: user={} service={}: {}", user_id, service, e)
        return None


async def get_case(
    case_id: str,
    user_id: Optional[str] = None,
    role: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """
    查询单个办件，按归属校验（P1-5 用户只能查询自己的办件）。

    Args:
        case_id: 办件编号
        user_id: 调用者用户 ID；传入时校验归属
        role: 调用者角色；admin 可跨用户查询

    Returns:
        办件字典；不存在、越权或 DB 不可用时返回 None
    """
    try:
        from database.connection import get_session_factory
        from database.models import Case
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(Case).where(Case.case_id == case_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            # 归属校验：非 admin 只能查自己的办件（越权与不存在同样返回 None，避免泄露存在性）
            if user_id and role != "admin" and row.user_id != user_id:
                logger.warning(
                    "越权查询办件: case={} caller={} owner={}",
                    case_id, user_id, row.user_id,
                )
                return None
        return _to_dict(row)
    except Exception as e:
        logger.warning("读取办件失败: {} — {}", case_id, e)
        return None


async def list_cases(
    user_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """列出用户最近的办件（按创建时间倒序）。"""
    try:
        from database.connection import get_session_factory
        from database.models import Case
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = (
                select(Case)
                .where(Case.user_id == user_id)
                .order_by(Case.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_dict(r) for r in rows]
    except Exception as e:
        logger.warning("列出办件失败: user={} — {}", user_id, e)
        return []


async def update_case_status(
    case_id: str,
    status: str,
    progress: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """
    更新办件状态（供后续真实业务流程推进状态用）。

    Args:
        case_id: 办件编号
        status: 新状态
        progress: 进度描述（不传则按状态映射默认文案）
        error_message: 失败原因（status=failed 时记录）

    Returns:
        更新后的办件字典；办件不存在或 DB 不可用时返回 None
    """
    try:
        from database.connection import get_session_factory
        from database.models import Case
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Case).where(Case.case_id == case_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            row.status = status
            if progress is not None:
                row.progress = progress
            else:
                row.progress = _DEFAULT_PROGRESS.get(status, f"当前状态: {status}")
            if error_message is not None:
                row.error_message = error_message
            await session.commit()
            await session.refresh(row)
        logger.info("办件状态更新: {} -> {}", case_id, status)
        return _to_dict(row)
    except Exception as e:
        logger.warning("更新办件状态失败: {} — {}", case_id, e)
        return None


_DEFAULT_PROGRESS: dict[str, str] = {
    "created": "办件已创建，等待分配处理人员",
    "processing": "办件处理中，正在审核提交材料",
    "reviewing": "材料审核完成，正在进行最终审批",
    "completed": "办件已完成，请留意短信通知领取结果",
    "failed": "办件处理失败，请咨询人工客服",
}
