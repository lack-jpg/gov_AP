"""
backend.services.conversation_service - 多轮对话会话与历史消息持久化

Author: le
Date: 2026/8/8
Version: 0.1
Task: Conversation CRUD + 消息追加 + 历史加载（供 /api/chat 多轮上下文与前端会话列表使用）

遵循仓库 DB 模式：函数内懒导入 get_session_factory + ORM，DB 不可用时优雅降级（返回空/False）。
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from tools.logger import get_logger

logger = get_logger(__name__)


def new_conversation_id() -> str:
    """生成会话 ID。"""
    return f"conv_{uuid.uuid4().hex[:12]}"


# ============================================================
# 会话 CRUD
# ============================================================


async def create_conversation(
    user_id: str,
    title: str = "新对话",
    conversation_id: Optional[str] = None,
) -> dict[str, Any]:
    """创建会话，返回 {conversation_id, title, created_at}。"""
    cid = conversation_id or new_conversation_id()
    try:
        from datetime import datetime, timezone

        from database.connection import get_session_factory
        from database.models import Conversation

        session_factory = get_session_factory()
        now = datetime.now(timezone.utc)
        async with session_factory() as session:
            conv = Conversation(
                conversation_id=cid,
                user_id=user_id,
                title=title or "新对话",
                created_at=now,
                updated_at=now,
            )
            session.add(conv)
            await session.commit()
        logger.info("会话创建: {} user={}", cid, user_id)
    except Exception as e:
        logger.warning("创建会话失败（将返回内存会话）: {}", e)
    return {
        "conversation_id": cid,
        "user_id": user_id,
        "title": title or "新对话",
    }


async def list_conversations(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """列出用户会话（按更新时间倒序，含 message_count 供前端过滤空会话）。"""
    try:
        from database.connection import get_session_factory
        from database.models import Conversation, ConversationMessage
        from sqlalchemy import func, select

        session_factory = get_session_factory()
        msg_count = (
            select(func.count(ConversationMessage.id))
            .where(ConversationMessage.conversation_id == Conversation.conversation_id)
            .scalar_subquery()
        )
        async with session_factory() as session:
            stmt = (
                select(Conversation, msg_count.label("message_count"))
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
        return [
            {
                "conversation_id": r[0].conversation_id,
                "title": r[0].title,
                "message_count": r[1] or 0,
                "created_at": r[0].created_at.isoformat() if r[0].created_at else "",
                "updated_at": r[0].updated_at.isoformat() if r[0].updated_at else "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("列出会话失败: {}", e)
        return []


async def get_conversation(conversation_id: str) -> Optional[dict[str, Any]]:
    """按 ID 取会话（不存在返回 None）。"""
    try:
        from database.connection import get_session_factory
        from database.models import Conversation
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Conversation).where(Conversation.conversation_id == conversation_id)
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "conversation_id": row.conversation_id,
            "user_id": row.user_id,
            "title": row.title,
        }
    except Exception as e:
        logger.warning("读取会话失败: {}", e)
        return None


async def update_conversation_title(conversation_id: str, title: str) -> None:
    """更新会话标题。"""
    try:
        from database.connection import get_session_factory
        from database.models import Conversation
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(Conversation).where(Conversation.conversation_id == conversation_id)
                )
            ).scalar_one_or_none()
            if row is not None:
                row.title = title
                await session.commit()
    except Exception as e:
        logger.warning("更新会话标题失败: {}", e)


# ============================================================
# 消息
# ============================================================


async def add_message(
    conversation_id: str,
    role: str,
    content: str,
    trace_id: str = "",
) -> None:
    """追加一条对话消息。"""
    if not content:
        return
    try:
        from database.connection import get_session_factory
        from database.models import ConversationMessage

        session_factory = get_session_factory()
        async with session_factory() as session:
            session.add(ConversationMessage(
                conversation_id=conversation_id,
                role=role,
                content=content[:8000],
                trace_id=trace_id,
            ))
            await session.commit()
    except Exception as e:
        logger.warning("追加对话消息失败: {}", e)


async def list_messages(conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """列出会话消息（按时间正序）。"""
    try:
        from database.connection import get_session_factory
        from database.models import ConversationMessage
        from sqlalchemy import select

        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.id.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "role": r.role,
                "content": r.content,
                "trace_id": r.trace_id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("列出会话消息失败: {}", e)
        return []


async def load_history(conversation_id: str, limit: int = 8) -> list[dict[str, str]]:
    """
    加载最近 N 条消息作为多轮上下文（user/assistant 交替文本）。

    Returns:
        [{"role": "user"|"assistant", "content": "..."}, ...]
    """
    messages = await list_messages(conversation_id, limit=limit * 2)
    # 只保留最近的完整轮次（user 开头）
    recent: list[dict[str, str]] = [
        {"role": m["role"], "content": m["content"]} for m in messages
    ]
    # 去掉孤立的 assistant 开头（历史截断导致）
    while recent and recent[0]["role"] != "user":
        recent.pop(0)
    return recent[-limit:]


def format_history_text(messages: list[dict[str, str]], max_turns: int = 4) -> str:
    """把多轮历史格式化为给 LLM 的文本（最近 max_turns 轮）。"""
    if not messages:
        return ""
    lines: list[str] = []
    for m in messages[-max_turns * 2:]:
        who = "用户" if m.get("role") == "user" else "助手"
        lines.append(f"{who}: {m.get('content', '')[:500]}")
    return "\n".join(lines)
