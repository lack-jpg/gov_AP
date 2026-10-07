"""Tenant-scoped conversation persistence; ownership checks fail closed."""
from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database.connection import get_session_factory
from database.models import Conversation, ConversationMessage
from tools.logger import get_logger

logger = get_logger(__name__)


def new_conversation_id() -> str:
    """Generate an opaque conversation ID."""
    return f"conv_{uuid.uuid4().hex[:12]}"


def _scope(tenant_id: str, user_id: str) -> tuple:
    """Require trusted tenant/owner; empty tenants quarantine legacy data."""
    if not all(isinstance(v, str) and v.strip() for v in (tenant_id, user_id)):
        raise HTTPException(401, "缺少有效的租户或用户身份")
    return Conversation.tenant_id == tenant_id, Conversation.user_id == user_id


def _storage_error(error: Exception) -> HTTPException:
    """Report failure without exposing SQL parameters or personal data."""
    logger.error("Conversation storage unavailable (type={})", type(error).__name__)
    return HTTPException(503, "会话存储暂时不可用，请稍后重试。")


def _serialize(row: Conversation) -> dict[str, Any]:
    return {
        "conversation_id": row.conversation_id, "user_id": row.user_id,
        "tenant_id": row.tenant_id, "title": row.title,
    }


async def create_conversation(
    user_id: str, title: str = "新对话", conversation_id: str | None = None,
    *, tenant_id: str,
) -> dict[str, Any]:
    """Create without overwriting or adopting another owner's conversation."""
    _scope(tenant_id, user_id)
    cid = conversation_id or new_conversation_id()
    try:
        async with get_session_factory()() as session:
            row = Conversation(
                conversation_id=cid, user_id=user_id, tenant_id=tenant_id,
                title=title or "新对话",
            )
            session.add(row)
            await session.commit()
            return _serialize(row)
    except IntegrityError:
        existing = await get_conversation(cid, user_id=user_id, tenant_id=tenant_id)
        if existing is not None:
            return existing
        raise HTTPException(404, "会话不存在或无权访问") from None
    except (SQLAlchemyError, OSError) as error:
        raise _storage_error(error) from None


async def list_conversations(
    user_id: str, limit: int = 50, *, tenant_id: str,
) -> list[dict[str, Any]]:
    """List only the authenticated owner's conversations within their tenant."""
    scope = _scope(tenant_id, user_id)
    count = (
        select(func.count(ConversationMessage.id))
        .where(ConversationMessage.conversation_id == Conversation.conversation_id,
               ConversationMessage.tenant_id == Conversation.tenant_id)
        .scalar_subquery()
    )
    try:
        async with get_session_factory()() as session:
            rows = (await session.execute(
                select(Conversation, count.label("message_count"))
                .where(*scope).order_by(Conversation.updated_at.desc()).limit(limit)
            )).all()
            serialized: list[dict[str, Any]] = []
            for raw_row, raw_total in rows:
                # select() 的 Row 在无 sqlalchemy mypy 插件时被推成 object
                conversation = cast(Conversation, raw_row)
                total = cast(int | None, raw_total)
                serialized.append({
                    **_serialize(conversation),
                    "message_count": total or 0,
                    "created_at": conversation.created_at.isoformat(),
                    "updated_at": conversation.updated_at.isoformat(),
                })
            return serialized
    except (SQLAlchemyError, OSError) as error:
        raise _storage_error(error) from None


async def get_conversation(
    conversation_id: str, *, user_id: str, tenant_id: str,
) -> dict[str, Any] | None:
    """Return None for absent/foreign conversations, never for a DB outage."""
    scope = _scope(tenant_id, user_id)
    try:
        async with get_session_factory()() as session:
            row = (await session.execute(select(Conversation).where(
                Conversation.conversation_id == conversation_id, *scope,
            ))).scalar_one_or_none()
            return _serialize(row) if row is not None else None
    except (SQLAlchemyError, OSError) as error:
        raise _storage_error(error) from None


async def update_conversation_title(
    conversation_id: str, title: str, *, user_id: str, tenant_id: str,
) -> None:
    """Update only after verifying both tenant and owner."""
    scope = _scope(tenant_id, user_id)
    try:
        async with get_session_factory()() as session:
            row = (await session.execute(select(Conversation).where(
                Conversation.conversation_id == conversation_id, *scope,
            ))).scalar_one_or_none()
            if row is None:
                raise HTTPException(404, "会话不存在或无权访问")
            row.title = title
            await session.commit()
    except (SQLAlchemyError, OSError) as error:
        raise _storage_error(error) from None


async def add_message(
    conversation_id: str, role: str, content: str, trace_id: str = "",
    *, user_id: str, tenant_id: str,
) -> None:
    """Verify ownership in the write transaction before appending a message."""
    scope = _scope(tenant_id, user_id)
    if not content:
        return
    try:
        async with get_session_factory()() as session:
            owner = (await session.execute(select(Conversation.id).where(
                Conversation.conversation_id == conversation_id, *scope,
            ))).scalar_one_or_none()
            if owner is None:
                raise HTTPException(404, "会话不存在或无权访问")
            session.add(ConversationMessage(
                conversation_id=conversation_id, tenant_id=tenant_id,
                role=role, content=content[:8000], trace_id=trace_id,
            ))
            await session.commit()
    except (SQLAlchemyError, OSError) as error:
        raise _storage_error(error) from None


async def list_messages(
    conversation_id: str, limit: int = 100, *, user_id: str, tenant_id: str,
    newest: bool = False,
) -> list[dict[str, Any]]:
    """Read with matching message tenant, conversation tenant and owner."""
    scope = _scope(tenant_id, user_id)
    try:
        async with get_session_factory()() as session:
            rows = (await session.execute(
                select(ConversationMessage).join(
                    Conversation,
                    (Conversation.conversation_id == ConversationMessage.conversation_id)
                    & (Conversation.tenant_id == ConversationMessage.tenant_id),
                ).where(ConversationMessage.conversation_id == conversation_id, *scope)
                .order_by(ConversationMessage.id.desc() if newest else ConversationMessage.id.asc())
                .limit(limit)
            )).scalars().all()
            if newest:
                rows = list(reversed(rows))
            return [
                {"role": row.role, "content": row.content, "trace_id": row.trace_id,
                 "created_at": row.created_at.isoformat()}
                for row in rows
            ]
    except (SQLAlchemyError, OSError) as error:
        raise _storage_error(error) from None


async def load_history(
    conversation_id: str, limit: int = 8, *, user_id: str, tenant_id: str,
) -> list[dict[str, str]]:
    """Load recent owned messages in chronological order for the model."""
    messages = await list_messages(
        conversation_id, limit=limit, user_id=user_id, tenant_id=tenant_id, newest=True,
    )
    recent = [{"role": m["role"], "content": m["content"]} for m in messages]
    while recent and recent[0]["role"] != "user":
        recent.pop(0)
    return recent


def format_history_text(messages: list[dict[str, str]], max_turns: int = 4) -> str:
    """Format recent turns for planning and summarization."""
    if not messages:
        return ""
    lines = []
    for message in messages[-max_turns * 2:]:
        who = "用户" if message.get("role") == "user" else "助手"
        lines.append(f"{who}: {message.get('content', '')[:500]}")
    return "\n".join(lines)
