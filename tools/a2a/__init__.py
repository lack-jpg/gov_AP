"""
a2a - Agent-to-Agent: cross-domain Agent communication protocol

A2A (Agent-to-Agent) 模块提供跨域 Agent 协同能力，包括：
- protocol: A2A 协议定义（AgentCard, A2AMessage, A2ATaskRequest/Response）
- task: 任务状态机（created→submitted→working→completed/failed/timeout）
- registry: 外部 Agent 注册中心（register, discover, health_check）
- connector: A2A 连接器（send_task, check_status, cancel_task）
- callback: 回调处理器（接收外部 Agent 结果，恢复 LangGraph）
- mock_agents: 模拟外部 Agent（housing_agent, fund_agent）

Author: le
Date: 2026/7/29
Version: 0.2
Task: A2A package initialization — unified exports
"""

from tools.a2a.protocol import (
    # Enums
    A2AMessageType,
    AgentHealth,
    A2ATaskStatus,
    # Protocol Models
    AgentCard,
    A2AMessage,
    A2ATaskRequest,
    A2ATaskResponse,
    A2AStatusQuery,
    A2AStatusUpdate,
    # Re-exports
    A2ATaskRecord,
)

from tools.a2a.task import (
    TaskStateMachine,
    TaskStore,
    InvalidTransitionError,
    get_task_store,
)

from tools.a2a.registry import (
    ExternalAgentRegistry,
    get_external_registry,
    initialize_default_agents,
)

from tools.a2a.connector import (
    A2AConnector,
    get_a2a_connector,
)

from tools.a2a.callback import (
    A2ACallbackHandler,
    get_callback_handler,
    create_callback_router,
    CallbackRequest,
    CallbackResponse,
)

from tools.a2a.mock_agents.housing_agent import (
    HousingAgent,
    get_housing_agent,
    query_property_stub,
    register_property_stub,
)

from tools.a2a.mock_agents.fund_agent import (
    FundAgent,
    get_fund_agent,
    query_fund_stub,
    query_fund_detail_stub,
)


__all__ = [
    # Protocol
    "A2AMessageType",
    "AgentHealth",
    "A2ATaskStatus",
    "AgentCard",
    "A2AMessage",
    "A2ATaskRequest",
    "A2ATaskResponse",
    "A2AStatusQuery",
    "A2AStatusUpdate",
    "A2ATaskRecord",
    # Task
    "TaskStateMachine",
    "TaskStore",
    "InvalidTransitionError",
    "get_task_store",
    # Registry
    "ExternalAgentRegistry",
    "get_external_registry",
    "initialize_default_agents",
    # Connector
    "A2AConnector",
    "get_a2a_connector",
    # Callback
    "A2ACallbackHandler",
    "get_callback_handler",
    "create_callback_router",
    "CallbackRequest",
    "CallbackResponse",
    # Mock Agents
    "HousingAgent",
    "get_housing_agent",
    "query_property_stub",
    "register_property_stub",
    "FundAgent",
    "get_fund_agent",
    "query_fund_stub",
    "query_fund_detail_stub",
]
