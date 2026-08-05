"""
backend.middleware.rbac - RBAC middleware: role-based access control for MCP tools and API endpoints

Author: le
Date: 2026/7/29
Version: 0.3
Task: Implement role-based permission checking middleware

设计原则（来自 CLAUDE.md）:
  - MCP 不负责用户权限/RBAC
  - 权限由 Gateway Middleware 统一完成
  - 支持 API 端点 + MCP Tool 两级权限控制
"""
from __future__ import annotations

from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional

from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 角色定义
# ============================================================


class Role(str, Enum):
    """系统角色"""

    ADMIN = "admin"      # 管理员 — 全部权限
    AGENT = "agent"      # 系统 Agent — 可调用所有 API 和 Tool
    USER = "user"        # 普通用户 — 受限访问
    GUEST = "guest"      # 访客 — 只读、仅公开端点


# 角色层级（用于比较）
_ROLE_HIERARCHY: dict[Role, int] = {
    Role.ADMIN: 100,
    Role.AGENT: 80,
    Role.USER: 50,
    Role.GUEST: 10,
}


# ============================================================
# 权限定义
# ============================================================


class Permission(str, Enum):
    """细粒度权限"""

    # ── API 端点权限 ──
    CHAT_SEND = "chat:send"                # /api/chat
    AGENT_STATUS = "agent:status"           # /api/agent/status/{trace_id}
    A2A_CALLBACK = "a2a:callback"          # /api/a2a/callback（系统间调用）
    DASHBOARD_VIEW = "dashboard:view"       # /api/dashboard/overview
    EVALUATION_VIEW = "evaluation:view"     # /api/evaluation/report/{version}

    # ── MCP Tool 权限 ──
    TOOL_POLICY_SEARCH = "tool:policy:search"        # search_policy
    TOOL_POLICY_DETAIL = "tool:policy:detail"        # get_policy_detail
    TOOL_MATERIAL_EXTRACT = "tool:material:extract"   # extract_entity
    TOOL_MATERIAL_CHECK = "tool:material:check"       # check_material
    TOOL_WORKFLOW_CREATE = "tool:workflow:create"    # create_case
    TOOL_WORKFLOW_STATUS = "tool:workflow:status"     # query_status

    # ── 管理权限 ──
    ADMIN_ALL = "admin:all"                # 全部管理权限
    ADMIN_USERS = "admin:users"            # 用户管理
    ADMIN_CONFIG = "admin:config"          # 系统配置


# ============================================================
# 角色 → 权限映射
# ============================================================


# 每个角色拥有的权限集合
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        # admin 拥有全部权限
        Permission.CHAT_SEND,
        Permission.AGENT_STATUS,
        Permission.A2A_CALLBACK,
        Permission.DASHBOARD_VIEW,
        Permission.EVALUATION_VIEW,
        Permission.TOOL_POLICY_SEARCH,
        Permission.TOOL_POLICY_DETAIL,
        Permission.TOOL_MATERIAL_EXTRACT,
        Permission.TOOL_MATERIAL_CHECK,
        Permission.TOOL_WORKFLOW_CREATE,
        Permission.TOOL_WORKFLOW_STATUS,
        Permission.ADMIN_ALL,
        Permission.ADMIN_USERS,
        Permission.ADMIN_CONFIG,
    },
    Role.AGENT: {
        # Agent 可访问所有业务 API 和 MCP Tool
        Permission.CHAT_SEND,
        Permission.AGENT_STATUS,
        Permission.A2A_CALLBACK,
        Permission.DASHBOARD_VIEW,
        Permission.EVALUATION_VIEW,
        Permission.TOOL_POLICY_SEARCH,
        Permission.TOOL_POLICY_DETAIL,
        Permission.TOOL_MATERIAL_EXTRACT,
        Permission.TOOL_MATERIAL_CHECK,
        Permission.TOOL_WORKFLOW_CREATE,
        Permission.TOOL_WORKFLOW_STATUS,
    },
    Role.USER: {
        # 普通用户只能对话和查询状态
        Permission.CHAT_SEND,
        Permission.AGENT_STATUS,
        # MCP Tool — 用户通过 Agent 间接使用，受限于 Agent 调用链
        Permission.TOOL_POLICY_SEARCH,
        Permission.TOOL_MATERIAL_CHECK,
        Permission.TOOL_WORKFLOW_STATUS,
    },
    Role.GUEST: {
        # 访客：仅限公开查询
        Permission.AGENT_STATUS,
    },
}


# API 端点 → 所需权限
ENDPOINT_PERMISSIONS: dict[str, Permission] = {
    "/api/chat": Permission.CHAT_SEND,
    "/api/agent/status": Permission.AGENT_STATUS,  # 前缀匹配
    "/api/a2a/callback": Permission.A2A_CALLBACK,
    "/api/dashboard/overview": Permission.DASHBOARD_VIEW,
    "/api/evaluation/report": Permission.EVALUATION_VIEW,  # 前缀匹配
}

# 公开端点（无需鉴权）
PUBLIC_ENDPOINTS: set[str] = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/a2a/callback",  # A2A callback 通常来自内部系统，RBAC 在 callback handler 内部处理
}


# ============================================================
# 核心权限检查
# ============================================================


def has_permission(role: Role | str, permission: Permission) -> bool:
    """
    检查指定角色是否拥有某权限。

    Args:
        role: 角色（Role 枚举或字符串）
        permission: 要检查的权限

    Returns:
        True 表示有权限
    """
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return False

    permissions = ROLE_PERMISSIONS.get(role, set())
    return permission in permissions


def has_role(user_role: Role | str, required_role: Role) -> bool:
    """
    检查用户角色层级是否 >= 所需角色。

    Args:
        user_role: 用户当前角色
        required_role: 所需最低角色

    Returns:
        True 表示满足角色要求
    """
    if isinstance(user_role, str):
        try:
            user_role = Role(user_role)
        except ValueError:
            return False

    user_level = _ROLE_HIERARCHY.get(user_role, 0)
    required_level = _ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level


def get_permissions_for_role(role: Role | str) -> set[Permission]:
    """获取某角色的全部权限"""
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return set()
    return ROLE_PERMISSIONS.get(role, set())


# ============================================================
# FastAPI 依赖注入
# ============================================================


def require_role(required_role: Role) -> Callable:
    """
    FastAPI 依赖：要求用户具有指定角色。

    用法:
        @router.get("/admin")
        async def admin_endpoint(user=Depends(require_role(Role.ADMIN))): ...

    Args:
        required_role: 所需角色

    Returns:
        FastAPI 依赖函数
    """

    async def _check_role(request: Request) -> dict[str, str]:
        user_role_str = getattr(request.state, "user_role", None)
        user_id = getattr(request.state, "user_id", "unknown")

        if user_role_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="未认证 — 请先登录",
            )

        try:
            user_role = Role(user_role_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无效的角色: {user_role_str}",
            )

        if not has_role(user_role, required_role):
            logger.warning(
                "RBAC denied: user={user}, role={role}, required={required}",
                user=user_id, role=user_role_str, required=required_role.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 需要 {required_role.value} 角色，当前为 {user_role_str}",
            )

        return {"user_id": user_id, "role": user_role_str}

    return _check_role


def require_permission(permission: Permission) -> Callable:
    """
    FastAPI 依赖：要求用户具有指定权限。

    用法:
        @router.get("/dashboard")
        async def dashboard(user=Depends(require_permission(Permission.DASHBOARD_VIEW))): ...

    Args:
        permission: 所需权限

    Returns:
        FastAPI 依赖函数
    """

    async def _check_permission(request: Request) -> dict[str, str]:
        user_role_str = getattr(request.state, "user_role", None)
        user_id = getattr(request.state, "user_id", "unknown")

        if user_role_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="未认证 — 请先登录",
            )

        try:
            user_role = Role(user_role_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无效的角色: {user_role_str}",
            )

        if not has_permission(user_role, permission):
            logger.warning(
                "RBAC denied: user={user}, role={role}, permission={perm}",
                user=user_id, role=user_role_str, perm=permission.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 缺少 {permission.value} 权限",
            )

        return {"user_id": user_id, "role": user_role_str}

    return _check_permission


# ============================================================
# MCP Tool 权限检查（供 Gateway 调用）
# ============================================================


# MCP Tool 名称 → 所需权限
MCP_TOOL_PERMISSIONS: dict[str, Permission] = {
    "search_policy": Permission.TOOL_POLICY_SEARCH,
    "get_policy_detail": Permission.TOOL_POLICY_DETAIL,
    "extract_entity": Permission.TOOL_MATERIAL_EXTRACT,
    "check_material": Permission.TOOL_MATERIAL_CHECK,
    "create_case": Permission.TOOL_WORKFLOW_CREATE,
    "query_status": Permission.TOOL_WORKFLOW_STATUS,
}


def check_mcp_tool_access(role: str, tool_name: str, raise_on_deny: bool = False) -> bool:
    """
    检查用户是否有权限调用指定 MCP Tool。

    由 MCP Gateway 在转发 Tool Call 之前调用。

    Args:
        role: 用户角色
        tool_name: MCP Tool 名称
        raise_on_deny: 权限不足时是否抛出 PermissionError

    Returns:
        True 表示有权限

    Raises:
        PermissionError: raise_on_deny=True 且权限不足时抛出
    """
    permission = MCP_TOOL_PERMISSIONS.get(tool_name)
    if permission is None:
        # 未知 Tool — 默认允许（或按安全策略改为拒绝）
        logger.warning("MCP Tool 未注册权限: {}", tool_name)
        return True

    if not has_permission(role, permission):
        if raise_on_deny:
            raise PermissionError(
                f"角色 '{role}' 无权调用 MCP Tool '{tool_name}'（需要权限: {permission.value}）"
            )
        return False

    return True


# ============================================================
# RBAC 中间件 — 自动端点级权限检查
# ============================================================


class RBACMiddleware(BaseHTTPMiddleware):
    """
    FastAPI RBAC 中间件 — 自动检查端点权限。

    根据 ENDPOINT_PERMISSIONS 配置，自动拦截未授权的 API 请求。

    用法:
        app.add_middleware(RBACMiddleware)

    注意：
    - 仅检查 HTTP API 端点
    - MCP Tool 权限由 Gateway 通过 check_mcp_tool_access() 单独校验
    - 公开端点（PUBLIC_ENDPOINTS）不做检查
    """

    def __init__(self, app=None, **kwargs):
        super().__init__(app, **kwargs)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # ── 跳过公开端点 ──
        if path in PUBLIC_ENDPOINTS:
            return await call_next(request)

        # ── 查找端点权限 ──
        required_perm: Optional[Permission] = None

        # 精确匹配
        if path in ENDPOINT_PERMISSIONS:
            required_perm = ENDPOINT_PERMISSIONS[path]
        else:
            # 前缀匹配（适用于 /api/agent/status/{trace_id} 等动态路径）
            for prefix, perm in ENDPOINT_PERMISSIONS.items():
                if path.startswith(prefix):
                    required_perm = perm
                    break

        # 无权限要求的端点 — 允许通过
        if required_perm is None:
            return await call_next(request)

        # ── 检查用户角色 ──
        user_role_str = getattr(request.state, "user_role", None)

        if user_role_str is None:
            logger.warning("RBAC: request.state.user_role 未设置 — path={}", path)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="未认证，请提供有效的 Bearer Token",
            )

        try:
            user_role = Role(user_role_str)
        except ValueError:
            logger.warning("RBAC: 未知角色 {} — path={}", user_role_str, path)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"未知的角色类型: {user_role_str}",
            )

        if not has_permission(user_role, required_perm):
            logger.warning(
                "RBAC denied: role={role}, path={path}, required={perm}",
                role=user_role_str, path=path, perm=required_perm.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权访问此端点（需要权限: {required_perm.value}）",
            )

        return await call_next(request)


# ============================================================
# 便捷函数 — 装饰器
# ============================================================


def require_role_decorator(required_role: Role):
    """
    装饰器：要求调用者具有指定角色。

    适用于非 FastAPI 依赖注入场景（如普通函数、类方法）。

    用法:
        @require_role_decorator(Role.ADMIN)
        async def delete_user(user_id: str, caller_role: str): ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 kwargs 中提取 caller_role
            caller_role = kwargs.get("caller_role", "guest")
            if not has_role(caller_role, required_role):
                raise PermissionError(
                    f"角色 '{caller_role}' 无权执行此操作（需要 {required_role.value}）"
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# Smoke Test — python -m backend.middleware.rbac
# ============================================================

if __name__ == "__main__":
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

    # ── 1. Role 枚举 ──
    section("1. Role 枚举")
    check("ADMIN == 'admin'", Role.ADMIN == "admin")
    check("AGENT == 'agent'", Role.AGENT == "agent")
    check("USER == 'user'", Role.USER == "user")
    check("GUEST == 'guest'", Role.GUEST == "guest")
    check("Role.ADMIN.value == 'admin'", Role.ADMIN.value == "admin")

    # ── 2. 角色层级 ──
    section("2. 角色层级")
    check("admin > agent", has_role(Role.ADMIN, Role.AGENT))
    check("admin > user", has_role(Role.ADMIN, Role.USER))
    check("agent > user", has_role(Role.AGENT, Role.USER))
    check("user > guest", has_role(Role.USER, Role.GUEST))
    check("guest < user", not has_role(Role.GUEST, Role.USER))
    check("user < admin", not has_role(Role.USER, Role.ADMIN))
    check("相同角色", has_role(Role.ADMIN, Role.ADMIN))

    # 字符串参数
    check("'admin' > 'user'", has_role("admin", Role.USER))
    check("invalid role → False", not has_role("invalid", Role.USER))

    # ── 3. Permission 枚举 ──
    section("3. Permission 枚举")
    check("CHAT_SEND = 'chat:send'", Permission.CHAT_SEND == "chat:send")
    check("DASHBOARD_VIEW = 'dashboard:view'", Permission.DASHBOARD_VIEW == "dashboard:view")
    check("TOOL_POLICY_SEARCH = 'tool:policy:search'", Permission.TOOL_POLICY_SEARCH == "tool:policy:search")

    # ── 4. has_permission ──
    section("4. has_permission — 角色权限检查")
    check("admin: chat:send", has_permission(Role.ADMIN, Permission.CHAT_SEND))
    check("admin: admin:all", has_permission(Role.ADMIN, Permission.ADMIN_ALL))
    check("admin: tool:policy:search", has_permission(Role.ADMIN, Permission.TOOL_POLICY_SEARCH))

    check("agent: chat:send", has_permission(Role.AGENT, Permission.CHAT_SEND))
    check("agent: tool:material:check", has_permission(Role.AGENT, Permission.TOOL_MATERIAL_CHECK))
    check("agent: admin:all → NO", not has_permission(Role.AGENT, Permission.ADMIN_ALL))
    check("agent: admin:users → NO", not has_permission(Role.AGENT, Permission.ADMIN_USERS))

    check("user: chat:send", has_permission(Role.USER, Permission.CHAT_SEND))
    check("user: agent:status", has_permission(Role.USER, Permission.AGENT_STATUS))
    check("user: dashboard:view → NO", not has_permission(Role.USER, Permission.DASHBOARD_VIEW))
    check("user: tool:workflow:create → NO", not has_permission(Role.USER, Permission.TOOL_WORKFLOW_CREATE))

    check("guest: agent:status", has_permission(Role.GUEST, Permission.AGENT_STATUS))
    check("guest: chat:send → NO", not has_permission(Role.GUEST, Permission.CHAT_SEND))
    check("guest: tool:policy:search → NO", not has_permission(Role.GUEST, Permission.TOOL_POLICY_SEARCH))

    # 字符串角色参数
    check("str 'admin': chat:send", has_permission("admin", Permission.CHAT_SEND))
    check("str 'user': dashboard → NO", not has_permission("user", Permission.DASHBOARD_VIEW))
    check("invalid str → False", not has_permission("manager", Permission.CHAT_SEND))

    # ── 5. get_permissions_for_role ──
    section("5. get_permissions_for_role")
    admin_perms = get_permissions_for_role(Role.ADMIN)
    check("admin 至少 10 个权限", len(admin_perms) >= 10)
    user_perms = get_permissions_for_role(Role.USER)
    check("user 至少 3 个权限", len(user_perms) >= 3)
    guest_perms = get_permissions_for_role(Role.GUEST)
    check("guest 至少 1 个权限", len(guest_perms) >= 1)

    # ── 6. MCP Tool 权限检查 ──
    section("6. check_mcp_tool_access")
    check("admin → search_policy", check_mcp_tool_access("admin", "search_policy"))
    check("agent → search_policy", check_mcp_tool_access("agent", "search_policy"))
    check("user → search_policy", check_mcp_tool_access("user", "search_policy"))
    check("guest → search_policy → False", not check_mcp_tool_access("guest", "search_policy"))

    # guest 无 create_case 权限
    check("guest → create_case → False", not check_mcp_tool_access("guest", "create_case"))

    # raise_on_deny=True 时抛出 PermissionError
    try:
        check_mcp_tool_access("guest", "create_case", raise_on_deny=True)
        check("guest → create_case (raise) — should raise", False, "没有抛出 PermissionError")
    except PermissionError:
        check("guest → create_case (raise) — PermissionError raised", True)

    check("user → query_status", check_mcp_tool_access("user", "query_status"))
    check("user → create_case → False", not check_mcp_tool_access("user", "create_case"))

    # 未知 Tool 默认允许
    check("unknown tool → True (默认允许)", check_mcp_tool_access("guest", "unknown_tool"))

    # ── 7. 端点权限映射 ──
    section("7. ENDPOINT_PERMISSIONS 映射")
    check("/api/chat → CHAT_SEND", ENDPOINT_PERMISSIONS.get("/api/chat") == Permission.CHAT_SEND)
    check("/api/dashboard/overview → DASHBOARD_VIEW",
          ENDPOINT_PERMISSIONS.get("/api/dashboard/overview") == Permission.DASHBOARD_VIEW)
    check("/api/evaluation/report → EVALUATION_VIEW",
          ENDPOINT_PERMISSIONS.get("/api/evaluation/report") == Permission.EVALUATION_VIEW)

    # ── 8. 公开端点 ──
    section("8. PUBLIC_ENDPOINTS")
    check("/health 是公开的", "/health" in PUBLIC_ENDPOINTS)
    check("/docs 是公开的", "/docs" in PUBLIC_ENDPOINTS)

    # ── 9. MCP_TOOL_PERMISSIONS ──
    section("9. MCP_TOOL_PERMISSIONS 映射")
    check("search_policy → TOOL_POLICY_SEARCH",
          MCP_TOOL_PERMISSIONS.get("search_policy") == Permission.TOOL_POLICY_SEARCH)
    check("extract_entity → TOOL_MATERIAL_EXTRACT",
          MCP_TOOL_PERMISSIONS.get("extract_entity") == Permission.TOOL_MATERIAL_EXTRACT)
    check("create_case → TOOL_WORKFLOW_CREATE",
          MCP_TOOL_PERMISSIONS.get("create_case") == Permission.TOOL_WORKFLOW_CREATE)

    # ── 10. require_role / require_permission 依赖函数存在 ──
    section("10. FastAPI 依赖函数")
    check("require_role 可调用", callable(require_role(Role.ADMIN)))
    check("require_permission 可调用", callable(require_permission(Permission.CHAT_SEND)))
    check("require_role_decorator 可调用", callable(require_role_decorator(Role.ADMIN)))

    # ── 11. RBACMiddleware 实例化 ──
    section("11. RBACMiddleware")
    mw = RBACMiddleware()
    check("RBACMiddleware 创建成功", mw is not None)
    check("__call__ 存在", hasattr(mw, "__call__"))

    # ── 12. require_role_decorator 装饰器 ──
    section("12. require_role_decorator 装饰器")
    import asyncio

    @require_role_decorator(Role.ADMIN)
    async def admin_only_action(**kwargs):
        return "ok"

    async def test_decorator():
        # admin 可以执行
        result = await admin_only_action(caller_role="admin")
        check("admin 可以执行 admin_only_action", result == "ok")

        # user 不能执行
        try:
            await admin_only_action(caller_role="user")
            check("user 执行 admin_only_action — should raise", False, "没有抛出异常")
        except PermissionError:
            check("user 执行 admin_only_action — PermissionError raised", True)

    asyncio.run(test_decorator())

    # ── 13. 边界情况 ──
    section("13. 边界情况")
    check("空字符串角色 → False", not has_permission("", Permission.CHAT_SEND))
    check("None-like 角色 → False", not has_permission("nobody", Permission.CHAT_SEND))
    check("ADMIN 等于自身字符串", Role("admin") == Role.ADMIN)
    try:
        Role("super_user")
        check("无效角色 → should raise", False, "没有抛出 ValueError")
    except ValueError:
        check("无效角色 → ValueError raised", True)

    # ── Summary ──
    section("SUMMARY")
    total = passed + failed
    print(f"\n  {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
        exit(1)
    else:
        print(" — all good")
        print(f"\n  Run with: python -m backend.middleware.rbac")
