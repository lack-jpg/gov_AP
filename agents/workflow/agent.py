"""
workflow.agent - Workflow Agent core: execute business processes via MCP

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement Workflow Agent with MCP tool calling for case management
"""
from __future__ import annotations

from typing import Any, Optional

from langchain_core.language_models import BaseChatModel

from orchestration.langgraph.state import AgentState
from tools.logger import get_logger, log_mcp_call

logger = get_logger(__name__)


class WorkflowAgent:
    """
    Workflow Agent — 业务流程执行。

    所有外部调用通过 MCP:
      Agent → MCP Client → MCP Gateway → MCP Server → Business API

    支持的 MCP 工具:
      - create_case: 创建办件 (workflow_server)
      - query_status: 查询进度 (workflow_server)

    当前实现: 模拟办件（MCP 待接入）
    TODO: 接入 MCP Client 进行真实调用

    使用方式:
        agent = WorkflowAgent()
        result = await agent.create_case(user_id="001", service="restaurant_license")
    """

    def __init__(self, mcp_client: Any = None):
        """
        Args:
            mcp_client: MCP 客户端实例（不传则用模拟模式）
        """
        self._mcp_client = mcp_client

    async def create_case(
        self,
        user_id: str,
        service: str,
        materials: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        创建办件。

        Args:
            user_id: 用户 ID
            service: 服务类型
            materials: 材料列表

        Returns:
            {case_id: str, status: str, service: str}
        """
        if self._mcp_client is not None:
            # TODO: 通过 MCP 调用真实业务系统
            # result = await self._mcp_client.call_tool(
            #     "create_case",
            #     {"user_id": user_id, "service": service}
            # )
            # log_mcp_call("workflow_server", "create_case", {...}, result, 100, "success")
            pass

        # 模拟模式
        import uuid
        case_id = f"CASE_{uuid.uuid4().hex[:8].upper()}"

        log_mcp_call(
            server_name="workflow_server",
            tool_name="create_case",
            input_args={"user_id": user_id, "service": service},
            output_result={"case_id": case_id, "status": "created"},
            latency_ms=100.0,
            status="success",
        )

        logger.info("办件创建: case_id={} service={}", case_id, service)
        return {
            "case_id": case_id,
            "status": "created",
            "service": service,
        }

    async def query_status(self, case_id: str) -> dict[str, Any]:
        """
        查询办件状态。

        Args:
            case_id: 办件 ID

        Returns:
            {case_id: str, status: str, progress: str}
        """
        if self._mcp_client is not None:
            # result = await self._mcp_client.call_tool("query_status", {"case_id": case_id})
            pass

        # 模拟模式
        statuses = ["created", "processing", "reviewing", "completed"]
        import random
        status = random.choice(statuses)

        log_mcp_call(
            server_name="workflow_server",
            tool_name="query_status",
            input_args={"case_id": case_id},
            output_result={"case_id": case_id, "status": status},
            latency_ms=50.0,
            status="success",
        )

        return {
            "case_id": case_id,
            "status": status,
            "progress": f"当前状态: {status}",
        }

    async def process(self, state: AgentState) -> AgentState:
        """
        LangGraph 节点接口。

        Args:
            state: 当前 AgentState

        Returns:
            更新后的 AgentState
        """
        user_id = "default_user"
        intent = state.get("intent", "business_license")

        result = await self.create_case(user_id=user_id, service=intent)
        logger.info("Workflow 完成: {}", result.get("case_id", "?"))
        return state
