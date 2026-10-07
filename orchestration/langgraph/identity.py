"""Stable, bounded checkpoint identifiers scoped to authenticated identities."""
from __future__ import annotations

import hashlib
import json


def checkpoint_thread_id(tenant_id: str, user_id: str, session_id: str) -> str:
    """Namespace a conversation/trace without delimiter collisions or raw PII."""
    if not all(isinstance(value, str) and value.strip() for value in (tenant_id, user_id, session_id)):
        raise ValueError("Checkpoint identity must be non-empty")
    payload = json.dumps([tenant_id, user_id, session_id], ensure_ascii=False)
    return "tenant-v1:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
