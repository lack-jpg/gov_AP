"""
database.auth_service - 用户认证服务：密码哈希、用户校验、默认管理员 seed

Author: le
Date: 2026/8/15
Version: 0.1
Task: User 表读写 + bcrypt 密码校验 + 默认管理员账号初始化
"""
from __future__ import annotations

from typing import Optional

import bcrypt
from sqlalchemy import select

from backend.config import get_settings
from database.connection import get_session_factory
from database.models import User
from tools.logger import get_logger

logger = get_logger(__name__)


def hash_password(password: str) -> str:
    """bcrypt 哈希密码（自动加盐，返回存储用哈希串）。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码与哈希是否匹配（哈希损坏时安全返回 False）。"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


async def get_user_by_username(username: str) -> Optional[User]:
    """按用户名查询用户，不存在返回 None。"""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()


async def seed_default_admin() -> None:
    """
    启动时初始化默认管理员账号（仅当 User 表为空 / 该账号不存在时创建）。

    账号来源配置项 AUTH_ADMIN_USERNAME / AUTH_ADMIN_PASSWORD，
    默认 admin / admin123。生产环境务必修改密码。
    """
    settings = get_settings()

    existing = await get_user_by_username(settings.auth_admin_username)
    if existing is not None:
        return

    factory = get_session_factory()
    async with factory() as session:
        session.add(
            User(
                username=settings.auth_admin_username,
                password_hash=hash_password(settings.auth_admin_password),
                role="admin",
                tenant_id=settings.auth_admin_tenant_id,
            )
        )
        await session.commit()

    logger.warning(
        "已创建默认管理员账号 username={}（生产环境请立即修改密码）",
        settings.auth_admin_username,
    )
