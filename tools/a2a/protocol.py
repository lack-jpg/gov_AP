"""
a2a.protocol - A2A Protocol: message format, agent card, task structure definitions

Author: le
Date: 2026/7/29
Version: 0.2
Task: Define A2A communication protocol and message schemas
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# 复用 state.py 中已定义的 A2ATaskStatus 枚举和 A2ATaskRecord 模型
from orchestration.langgraph.state import A2ATaskStatus, A2ATaskRecord


# ============================================================
# Enums
# ============================================================


class A2AMessageType(str, Enum):
    """A2A 消息类型"""
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    STATUS_QUERY = "status_query"
    STATUS_UPDATE = "status_update"
    CALLBACK = "callback"
    ERROR = "error"


class AgentHealth(str, Enum):
    """外部 Agent 健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# ============================================================
# Pydantic Models — A2A 协议层面
# ============================================================


class AgentCard(BaseModel):
    """
    外部 Agent 能力描述卡片。

    每个外部 Agent（如不动产系统、公积金系统）需提供一张卡片，
    描述其身份、可用技能和通信端点。
    卡片在注册时提交，供 Connector 发现和调用。
    """

    agent_id: str = Field(
        default_factory=lambda: f"ext_agent_{uuid.uuid4().hex[:8]}",
        description="外部 Agent 唯一标识，自动生成 (ext_agent_xxxxxxxx)",
    )
    name: str = Field(
        description="Agent 名称: housing_agent | fund_agent | medical_agent | ...",
    )
    display_name: str = Field(
        default="",
        description="Agent 中文显示名: 不动产系统Agent | 公积金系统Agent",
    )
    description: str = Field(
        default="",
        description="Agent 能力描述，供 Supervisor 发现和选择",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Agent 提供的技能列表: ['query_property', 'query_fund']",
    )
    endpoint: str = Field(
        default="",
        description="Agent 通信端点 URL: http://localhost:12201",
    )
    version: str = Field(
        default="0.1.0",
        description="Agent 版本号",
    )
    protocol_version: str = Field(
        default="1.0",
        description="A2A 协议版本",
    )
    timeout_ms: int = Field(
        default=30000,
        description="Agent 调用超时时间（毫秒）",
    )
    registered_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="注册时间 (ISO 8601 UTC)",
    )


class A2AMessage(BaseModel):
    """
    标准化 A2A 通信消息。

    所有 Agent 间通信都使用此消息格式，确保协议的统一性。
    """

    message_id: str = Field(
        default_factory=lambda: f"msg_{uuid.uuid4().hex[:8]}",
        description="消息唯一标识 (msg_xxxxxxxx)",
    )
    correlation_id: str = Field(
        default="",
        description="关联消息 ID，用于请求-响应配对",
    )
    task_id: str = Field(
        description="关联的 A2A 任务 ID",
    )
    message_type: A2AMessageType = Field(
        description="消息类型",
    )
    source_agent: str = Field(
        description="发送方 Agent 名称",
    )
    target_agent: str = Field(
        description="接收方 Agent 名称",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="消息载荷",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="消息创建时间 (ISO 8601 UTC)",
    )


class A2ATaskRequest(BaseModel):
    """
    发送给外部 Agent 的异步任务请求。

    由本系统（Gov AP）发出，携带回调地址供外部 Agent 完成后回报。
    """

    task_id: str = Field(
        default_factory=lambda: f"a2a_{uuid.uuid4().hex[:8]}",
        description="A2A 任务唯一标识 (a2a_xxxxxxxx)",
    )
    skill: str = Field(
        description="调用的技能: query_property | query_fund | query_medical | ...",
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="任务输入参数，如 {user_id: '001', property_id: 'X-123'}",
    )
    callback_url: str = Field(
        default="",
        description="外部 Agent 完成后的回调地址",
    )
    source_trace_id: str = Field(
        default="",
        description="源系统 trace_id，用于全链路追踪",
    )
    timeout_ms: int = Field(
        default=30000,
        description="任务超时时间（毫秒），外部 Agent 应在此时间内完成",
    )
    priority: int = Field(
        default=0,
        description="任务优先级，数字越大越优先",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="任务创建时间 (ISO 8601 UTC)",
    )


class A2ATaskResponse(BaseModel):
    """
    外部 Agent 返回的异步任务响应。

    在外部 Agent 完成任务后，通过 Callback 或同步返回此结构。
    """

    task_id: str = Field(
        description="关联的 A2A 任务 ID",
    )
    status: A2ATaskStatus = Field(
        description="任务完成状态: completed | failed | timeout",
    )
    artifact: Optional[dict[str, Any]] = Field(
        default=None,
        description="任务执行结果数据，失败时为 None",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="失败或超时时的错误信息",
    )
    completed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="任务完成时间 (ISO 8601 UTC)",
    )
    agent_name: str = Field(
        default="",
        description="执行任务的外部 Agent 名称",
    )
    duration_ms: float = Field(
        default=0.0,
        description="任务执行耗时（毫秒）",
    )


class A2AStatusQuery(BaseModel):
    """A2A 任务状态查询请求"""

    task_id: str = Field(
        description="要查询的 A2A 任务 ID",
    )


class A2AStatusUpdate(BaseModel):
    """A2A 任务状态更新（外部 Agent 主动推送）"""

    task_id: str = Field(
        description="A2A 任务 ID",
    )
    new_status: A2ATaskStatus = Field(
        description="新状态",
    )
    message: str = Field(
        default="",
        description="状态变更附加消息",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="状态更新时间 (ISO 8601 UTC)",
    )


# ============================================================
# Re-export from state.py（统一入口）
# ============================================================

__all__ = [
    # Enums
    "A2AMessageType",
    "AgentHealth",
    "A2ATaskStatus",
    # Protocol Models
    "AgentCard",
    "A2AMessage",
    "A2ATaskRequest",
    "A2ATaskResponse",
    "A2AStatusQuery",
    "A2AStatusUpdate",
    # Re-exports from state.py
    "A2ATaskRecord",
]


# ============================================================
# Smoke Test — python -m tools.a2a.protocol
# ============================================================

if __name__ == "__main__":
    import json

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

    # ── 1. Enums ──
    section("1. Enums")
    check("A2AMessageType 6 members", len(A2AMessageType) == 6)
    check("AgentHealth 4 members", len(AgentHealth) == 4)
    check("A2ATaskStatus 6 members", len(A2ATaskStatus) == 6)
    check("A2ATaskStatus.CREATED == 'created'", A2ATaskStatus.CREATED.value == "created")
    check("A2ATaskStatus.COMPLETED == 'completed'", A2ATaskStatus.COMPLETED.value == "completed")

    # ── 2. AgentCard ──
    section("2. AgentCard")
    card = AgentCard(
        name="housing_agent",
        display_name="不动产系统Agent",
        description="提供不动产登记和查询服务",
        skills=["query_property", "register_property"],
        endpoint="http://localhost:12201",
        version="1.2.0",
    )
    check("AgentCard.agent_id starts with ext_agent_", card.agent_id.startswith("ext_agent_"))
    check("AgentCard.name", card.name == "housing_agent")
    check("AgentCard.skills[0]", card.skills[0] == "query_property")
    check("AgentCard.endpoint", card.endpoint == "http://localhost:12201")

    card_dict = card.model_dump()
    check("AgentCard serializable", isinstance(card_dict, dict))
    card_json = card.model_dump_json()
    check("AgentCard JSON", isinstance(card_json, str))
    parsed = json.loads(card_json)
    check("AgentCard round-trip", parsed["name"] == "housing_agent")

    # ── 3. A2AMessage ──
    section("3. A2AMessage")
    msg = A2AMessage(
        task_id="a2a_test001",
        message_type=A2AMessageType.TASK_REQUEST,
        source_agent="gov_agent",
        target_agent="housing_agent",
        payload={"query": "查询房产"},
    )
    check("A2AMessage.msg_id starts with msg_", msg.message_id.startswith("msg_"))
    check("A2AMessage.task_id", msg.task_id == "a2a_test001")
    check("A2AMessage.type", msg.message_type == A2AMessageType.TASK_REQUEST)
    check("A2AMessage payload serializable", json.dumps(msg.model_dump()) is not None)

    # correlation_id 响应消息
    resp_msg = A2AMessage(
        correlation_id=msg.message_id,
        task_id="a2a_test001",
        message_type=A2AMessageType.TASK_RESPONSE,
        source_agent="housing_agent",
        target_agent="gov_agent",
        payload={"result": "found"},
    )
    check("A2AMessage.correlation", resp_msg.correlation_id == msg.message_id)

    # ── 4. A2ATaskRequest ──
    section("4. A2ATaskRequest")
    req = A2ATaskRequest(
        skill="query_property",
        input={"owner_name": "张三", "id_card": "110101199001011234"},
        callback_url="http://localhost:12200/api/a2a/callback",
        source_trace_id="trace_abc123",
    )
    check("A2ATaskRequest.task_id starts with a2a_", req.task_id.startswith("a2a_"))
    check("A2ATaskRequest.skill", req.skill == "query_property")
    check("A2ATaskRequest.callback_url set", "callback" in req.callback_url)
    check("A2ATaskRequest.timeout_ms default", req.timeout_ms == 30000)

    req_dict = req.model_dump()
    check("A2ATaskRequest round-trip", A2ATaskRequest.model_validate(req_dict).skill == "query_property")

    # ── 5. A2ATaskResponse ──
    section("5. A2ATaskResponse")
    resp = A2ATaskResponse(
        task_id=req.task_id,
        status=A2ATaskStatus.COMPLETED,
        artifact={"properties": [{"id": "X-001", "address": "成都市锦江区XX路100号"}]},
        agent_name="housing_agent",
        duration_ms=1520.0,
    )
    check("A2ATaskResponse.status == completed", resp.status == A2ATaskStatus.COMPLETED)
    check("A2ATaskResponse.artifact present", resp.artifact is not None)
    check("A2ATaskResponse.agent_name", resp.agent_name == "housing_agent")
    check("A2ATaskResponse.duration_ms", resp.duration_ms == 1520.0)

    # 失败响应
    fail_resp = A2ATaskResponse(
        task_id="a2a_fail001",
        status=A2ATaskStatus.FAILED,
        error_message="External agent timeout after 30s",
    )
    check("A2ATaskResponse failed", fail_resp.status == A2ATaskStatus.FAILED)
    check("A2ATaskResponse error_message", fail_resp.error_message is not None)
    check("A2ATaskResponse artifact None on fail", fail_resp.artifact is None)

    # ── 6. A2AStatusQuery / A2AStatusUpdate ──
    section("6. Status Query / Update")
    query = A2AStatusQuery(task_id="a2a_test001")
    check("A2AStatusQuery.task_id", query.task_id == "a2a_test001")

    update = A2AStatusUpdate(
        task_id="a2a_test001",
        new_status=A2ATaskStatus.WORKING,
        message="正在查询不动产登记信息...",
    )
    check("A2AStatusUpdate.new_status", update.new_status == A2ATaskStatus.WORKING)

    # ── 7. A2ATaskRecord (from state.py) ──
    section("7. A2ATaskRecord (re-export from state)")
    record = A2ATaskRecord(
        source_agent="workflow",
        target_agent="housing_agent",
        skill="query_property",
        input={"user_id": "001"},
    )
    check("A2ATaskRecord.task_id starts with a2a_", record.task_id.startswith("a2a_"))
    check("A2ATaskRecord.default status == CREATED", record.status == A2ATaskStatus.CREATED)
    check("A2ATaskRecord.artifact is None", record.artifact is None)

    # ── Summary ──
    section("SUMMARY")
    total = passed + failed
    print(f"\n  {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
        exit(1)
    else:
        print(" — all good")
        print("\n  Run with: python -m tools.a2a.protocol")
