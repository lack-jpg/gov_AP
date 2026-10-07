"""Regression tests for fail-closed inputs and tenant-scoped persistence.

SQLite executes the actual ORM queries. A small awaitable session adapter avoids
requiring a running PostgreSQL server for these ownership regression tests.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.api import dependencies as deps
from backend.config import get_settings
from backend.services import conversation_service as conversations
from database.models import Conversation, ConversationMessage
from orchestration.langgraph.identity import checkpoint_thread_id
from tests.test_api_routes import _make_client


@pytest.fixture
def conversation_db(monkeypatch):
    """Execute service queries against an isolated real relational database."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Conversation.__table__.create(engine)
    ConversationMessage.__table__.create(engine)

    class AwaitableSession:
        def __init__(self):
            self.session = Session(engine, expire_on_commit=False)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self.session.close()

        async def execute(self, statement):
            return self.session.execute(statement)

        def add(self, row):
            self.session.add(row)

        async def commit(self):
            self.session.commit()

    monkeypatch.setattr(conversations, "get_session_factory", lambda: AwaitableSession)
    monkeypatch.setattr("database.connection.get_session_factory", lambda: AwaitableSession)
    yield engine
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("failure", ["guardrail", "pii"])
async def test_input_failure_never_builds_graph(monkeypatch, stream, failure):
    """Neither inspection failure may fall back to sending the raw query."""
    def fail(*args, **kwargs):
        raise RuntimeError("sensitive 13812341234 provider detail")

    if failure == "guardrail":
        monkeypatch.setattr("governance.guardrail.GuardrailRunner.run_input", fail)
    else:
        monkeypatch.setattr("governance.pii.detect_pii", fail)
    graph = AsyncMock()
    monkeypatch.setattr(deps, "get_agent_graph", graph)
    kwargs = dict(user_query="13812341234", user_id="u", trace_id="t", settings=get_settings())
    with pytest.raises(HTTPException) as exc:
        if stream:
            async for _ in deps.stream_agent(**kwargs):
                pytest.fail("A failed guardrail must not emit a success event")
        else:
            await deps.execute_agent(**kwargs)
    assert exc.value.status_code == 503
    assert "13812341234" not in exc.value.detail
    graph.assert_not_called()


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
def test_guardrail_failure_api_error(monkeypatch, path):
    def fail(*args, **kwargs):
        raise RuntimeError("private detector detail")

    monkeypatch.setattr("governance.guardrail.GuardrailRunner.run_input", fail)
    response = _make_client().post(path, json={"user_query": "hello", "user_id": "u1"})
    if path.endswith("stream"):
        assert '"event": "error"' in response.text
        assert '"event": "final"' not in response.text
    else:
        assert response.status_code == 503
    assert "private detector detail" not in response.text


@pytest.mark.asyncio
async def test_reads_and_writes_are_scoped(conversation_db):
    a = {"tenant_id": "tenant-a", "user_id": "same-user"}
    b = {"tenant_id": "tenant-b", "user_id": "same-user"}
    await conversations.create_conversation(conversation_id="private", **a)
    await conversations.add_message("private", "user", "tenant-a secret", **a)
    assert await conversations.get_conversation("private", **b) is None
    assert await conversations.list_conversations(**b) == []
    assert await conversations.list_messages("private", **b) == []
    assert await conversations.load_history("private", **b) == []
    for wrong in (b, {"tenant_id": "tenant-a", "user_id": "other"}):
        for operation in (
            lambda wrong=wrong: conversations.create_conversation(conversation_id="private", **wrong),
            lambda wrong=wrong: conversations.add_message("private", "user", "injected", **wrong),
            lambda wrong=wrong: conversations.update_conversation_title("private", "hijacked", **wrong),
        ):
            with pytest.raises(HTTPException) as exc:
                await operation()
            assert exc.value.status_code == 404
    assert (await conversations.get_conversation("private", **a))["title"] == "新对话"
    assert [m["content"] for m in await conversations.list_messages("private", **a)] == ["tenant-a secret"]
    assert (await conversations.list_conversations(**a))[0]["message_count"] == 1


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
def test_foreign_conversation_never_reaches_agent(conversation_db, path):
    with Session(conversation_db) as session:
        session.add(Conversation(conversation_id="private", user_id="same", tenant_id="a", title="secret"))
        session.commit()
    response = _make_client(user_id="same", tenant_id="b").post(
        path, json={"user_query": "hello", "user_id": "same", "conversation_id": "private"},
    )
    if path.endswith("stream"):
        assert '"event": "error"' in response.text
        assert '"event": "final"' not in response.text
    else:
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_unavailable_ownership_check_is_not_missing(monkeypatch):
    def unavailable():
        raise OSError("DB unavailable with private connection details")

    monkeypatch.setattr(conversations, "get_session_factory", unavailable)
    with pytest.raises(HTTPException) as exc:
        await conversations.get_conversation("private", user_id="u", tenant_id="t")
    assert exc.value.status_code == 503
    assert "private connection" not in exc.value.detail


@pytest.mark.asyncio
async def test_history_uses_latest_owned_messages(conversation_db):
    identity = {"tenant_id": "t", "user_id": "u"}
    await conversations.create_conversation(conversation_id="c", **identity)
    for i in range(20):
        await conversations.add_message("c", "user", str(i), **identity)
    assert [m["content"] for m in await conversations.load_history("c", limit=4, **identity)] == ["16", "17", "18", "19"]


def test_checkpoint_namespace_is_stable_and_unambiguous():
    keys = {
        checkpoint_thread_id("a", "u", "c"),
        checkpoint_thread_id("b", "u", "c"),
        checkpoint_thread_id("a", "v", "c"),
        checkpoint_thread_id("a:u", "v", "c"),
        checkpoint_thread_id("a", "u:v", "c"),
    }
    assert len(keys) == 5
    assert all(len(key) <= 128 for key in keys)
    assert checkpoint_thread_id("a", "u", "c") == checkpoint_thread_id("a", "u", "c")
    with pytest.raises(ValueError):
        checkpoint_thread_id("", "u", "c")


@pytest.mark.asyncio
async def test_executors_share_scoped_checkpoint_identity(monkeypatch):
    captured = []

    class Graph:
        async def ainvoke(self, state, config):
            captured.append(config["configurable"]["thread_id"])
            assert state["checkpoint_thread_id"] == captured[-1]
            return state

        async def astream(self, state, config, **kwargs):
            yield await self.ainvoke(state, config)

    monkeypatch.setattr(deps, "get_agent_graph", AsyncMock(return_value=Graph()))
    monkeypatch.setattr("governance.trace.flush_trace_to_db", AsyncMock())
    kwargs = dict(user_query="hello", user_id="u", tenant_id="a", trace_id="t", conversation_id="c", settings=get_settings())
    await deps.execute_agent(**kwargs)
    async for _ in deps.stream_agent(**kwargs):
        pass
    kwargs["tenant_id"] = "b"
    await deps.execute_agent(**kwargs)
    assert captured[0] == captured[1] == checkpoint_thread_id("a", "u", "c")
    assert captured[2] != captured[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_history_pii_is_masked_before_graph(monkeypatch, stream):
    class Graph:
        async def ainvoke(self, state, config):
            assert "13812341234" not in str(state)
            assert "138****1234" in state["conversation_history"]
            return state

        async def astream(self, state, config, **kwargs):
            yield await self.ainvoke(state, config)

    graph = AsyncMock(return_value=Graph())
    monkeypatch.setattr(deps, "get_agent_graph", graph)
    monkeypatch.setattr("governance.trace.flush_trace_to_db", AsyncMock())
    kwargs = dict(user_query="hello", user_id="u", trace_id="t", settings=get_settings(),
                  prior_messages=[{"role": "user", "content": "联系我13812341234"}])
    if stream:
        async for _ in deps.stream_agent(**kwargs):
            pass
    else:
        await deps.execute_agent(**kwargs)
    graph.assert_called_once()


@pytest.mark.asyncio
async def test_a2a_hydrated_record_resumes_scoped_checkpoint(conversation_db, monkeypatch):
    """Persist/hydrate identity and locate the scoped checkpoint after restart."""
    from database.models import A2ATask
    from orchestration.langgraph.checkpointer import PostgresCheckpointer, _CheckpointRow
    from tools.a2a.task_store import PostgresTaskStore
    from tools.a2a.task import TaskStore

    A2ATask.__table__.create(conversation_db)
    _CheckpointRow.__table__.create(conversation_db)
    checkpointer = PostgresCheckpointer()
    thread = checkpoint_thread_id("t", "u", "conversation")
    with Session(conversation_db) as session:
        task = A2ATask(
            task_id="task-1", source_agent="workflow", source_trace_id="raw-trace",
            checkpoint_thread_id=thread, target_agent="housing", skill="query_property",
            status="submitted", input_json={},
        )
        session.add(task)
        session.add(_CheckpointRow(
            thread_id=thread, checkpoint_id="cp-1",
            checkpoint_json=checkpointer._serialize_typed({"channel_values": {"waiting_task_id": "task-1"}}),
            metadata_json=checkpointer._serialize_typed({}),
        ))
        session.commit()
        hydrated = PostgresTaskStore()._row_to_record(task)

    store = TaskStore()
    store.create(hydrated)
    monkeypatch.setattr("tools.a2a.task.get_task_store", lambda: store)
    resumed = await checkpointer.resume_from_a2a("task-1", max_retries=1)
    assert resumed is not None
    assert resumed.config["configurable"]["thread_id"] == thread
    # Legacy trace IDs must never be used as a fallback to an unscoped checkpoint.
    hydrated.checkpoint_thread_id = ""
    assert await checkpointer.resume_from_a2a("task-1", max_retries=1) is None


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
def test_ownership_outage_does_not_run_agent(monkeypatch, path):
    async def unavailable(*args, **kwargs):
        raise HTTPException(503, "会话存储暂时不可用，请稍后重试。")

    monkeypatch.setattr(conversations, "get_conversation", unavailable)
    graph = AsyncMock()
    monkeypatch.setattr(deps, "get_agent_graph", graph)
    response = _make_client().post(path, json={
        "user_id": "u1", "user_query": "hello", "conversation_id": "existing",
    })
    if path.endswith("stream"):
        assert '"event": "error"' in response.text
        assert '"event": "final"' not in response.text
    else:
        assert response.status_code == 503
    graph.assert_not_called()
