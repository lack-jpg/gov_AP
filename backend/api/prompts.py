"""
backend.api.prompts - Prompt 管理 API（P2-4）

Prompt Registry 的管理端点：查询、创建/更新、激活版本、从 DB 热重载。

读接口要求登录（get_user_id）；写/管理接口要求 ADMIN 角色（require_role）。
路由挂载：main.py 里 include_router(prompts_router, prefix="/api")，
完整路径为 /api/prompts*。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.dependencies import get_user_id
from backend.api.schemas import PromptCreateRequest
from backend.middleware.rbac import Role, require_role
from prompts.registry import PromptTemplate, get_registry
from tools.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/prompts", tags=["Prompt 管理"])


def _serialize_template(t: PromptTemplate) -> dict:
    """序列化 PromptTemplate（含 content），供管理 API 返回。"""
    return {
        "name": t.name,
        "agent_name": t.agent_name,
        "version": t.version,
        "content": t.content,
        "variables": t.variables,
        "is_active": t.is_active,
        "created_by": t.created_by,
        "created_at": t.created_at,
    }


@router.get("", summary="列出全部 Prompt 模板")
async def list_prompts(_: str = Depends(get_user_id)) -> dict:
    """列出所有模板名称、版本及当前活跃版本。"""
    registry = get_registry()
    names = sorted(registry.list_all().keys())
    items = []
    for name in names:
        versions = registry.list_versions(name)
        active = registry.get_active(name)
        items.append(
            {
                "name": name,
                "agent_name": active.agent_name if active else None,
                "versions": versions,
                "active_version": active.version if active else None,
            }
        )
    return {"items": items, "total": len(items)}


@router.get("/{name}/versions", summary="查询指定模板的版本列表")
async def list_prompt_versions(
    name: str,
    _: str = Depends(get_user_id),
) -> dict:
    """列出指定模板的所有版本，并返回活跃版本详情。"""
    registry = get_registry()
    if name not in registry.list_all():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt 模板不存在: {name}",
        )
    versions = registry.list_versions(name)
    active = registry.get_active(name)
    return {
        "name": name,
        "versions": versions,
        "active_version": active.version if active else None,
        "active": _serialize_template(active) if active else None,
    }


@router.post(
    "",
    summary="创建/更新 Prompt 模板",
    status_code=status.HTTP_201_CREATED,
)
async def create_prompt(
    body: PromptCreateRequest,
    admin: dict = Depends(require_role(Role.ADMIN)),
) -> dict:
    """新建或覆盖模板；若 is_active=true，同模板其他版本自动停用。"""
    registry = get_registry()
    template = PromptTemplate(
        name=body.name,
        agent_name=body.agent_name,
        version=body.version,
        content=body.content,
        variables=body.variables or [],
        is_active=body.is_active,
        created_by=admin.get("user_id", "admin"),
    )
    registry.register(template)
    if body.is_active:
        registry.activate_version(body.name, body.version)

    # 持久化（DB 不可用时返回 0，内存仍生效）
    saved = await registry.flush_to_db(body.name)
    logger.info(
        "Prompt 已创建/更新: {} v{} by {} (db_saved={})",
        body.name, body.version, admin.get("user_id"), saved,
    )
    message = f"模板 {body.name} {body.version} 已保存"
    if not saved:
        message += "（DB 写入失败，仅内存生效）"
    return {
        "success": True,
        "message": message,
        "name": body.name,
        "version": body.version,
    }


@router.post("/{name}/{version}/activate", summary="激活指定版本")
async def activate_prompt_version(
    name: str,
    version: str,
    admin: dict = Depends(require_role(Role.ADMIN)),
) -> dict:
    """将指定版本设为活跃，并停用同模板其他版本。"""
    registry = get_registry()
    if name not in registry.list_all() or version not in registry.list_versions(name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 {name} 版本 {version} 不存在",
        )
    ok = registry.activate_version(name, version)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"激活失败: {name} v{version}",
        )
    saved = await registry.flush_to_db(name)
    logger.info(
        "Prompt 版本切换: {} → v{} by {} (db_saved={})",
        name, version, admin.get("user_id"), saved,
    )
    return {
        "success": True,
        "message": f"{name} 已切换到 {version}",
        "db_saved": bool(saved),
    }


@router.post("/reload", summary="从数据库热重载模板")
async def reload_prompts(
    admin: dict = Depends(require_role(Role.ADMIN)),
) -> dict:
    """清空内存注册表，从数据库重建；DB 空表时把内置默认模板落库。"""
    from prompts.registry import reset_registry

    reset_registry()
    registry = get_registry()
    loaded = await registry.load_from_db()
    if loaded == 0:
        await registry.flush_to_db()
        loaded = await registry.load_from_db()
    logger.info(
        "Prompt 注册表热重载 by {}: 加载 {} 条",
        admin.get("user_id"), loaded,
    )
    return {
        "success": True,
        "loaded": loaded,
        "message": f"已从数据库加载 {loaded} 条模板",
    }
