"""
workflow.agent - Workflow Agent core: execute business processes via MCP

Author: le
Date: 2026/7/29
Version: 0.1
Task: Implement Workflow Agent with MCP tool calling for case management
"""
from __future__ import annotations

import uuid
from typing import Any, Optional


from orchestration.langgraph.state import AgentState
from tools.logger import get_logger, log_mcp_call

logger = get_logger(__name__)


class WorkflowUnavailable(Exception):
    """办件服务不可用。未允许 stub 时不得伪造办件号。"""


class WorkflowAgent:
    """
    Workflow Agent — 业务流程执行。

    所有外部调用通过 MCP:
      Agent → MCP Client → MCP Gateway → MCP Server → Business API

    支持的 MCP 工具:
      - create_case: 创建办件 (workflow_server)
      - query_status: 查询进度 (workflow_server)

    有 MCP 客户端时只使用工具返回的 case_id。
    无客户端时，仅当 allow_stub 或配置 MCP_ALLOW_STUB 为真才返回 mode=stub。

    使用方式:
        agent = WorkflowAgent(mcp_client=client)
        result = await agent.create_case(user_id="001", service="restaurant_license")
    """

    def __init__(self, mcp_client: Any = None, allow_stub: Optional[bool] = None):
        """
        Args:
            mcp_client: MCP 客户端实例。为空且未允许 stub 时，创建办件会失败。
            allow_stub: 是否允许本地模拟。None 时读取 MCP_ALLOW_STUB，默认关闭。
        """
        self._mcp_client = mcp_client
        self._allow_stub = allow_stub

    def _stub_allowed(self) -> bool:
        if self._allow_stub is not None:
            return self._allow_stub
        from backend.config import get_settings

        return bool(get_settings().mcp_allow_stub)

    async def create_case(
        self,
        user_id: str,
        service: str,
        materials: Optional[list[str]] = None,
        tenant_id: str = "",
        trace_id: str = "",
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
        arguments = {
            "user_id": user_id,
            "service": service,
            "materials": materials or [],
            "tenant_id": tenant_id,
        }
        if self._mcp_client is not None:
            result = await self._mcp_client.call_tool(
                "workflow_server",
                "create_case",
                arguments,
                trace_id=trace_id,
            )
            case_id = (result or {}).get("case_id", "")
            if not case_id:
                raise WorkflowUnavailable("办件工具未返回 case_id")
            logger.info("办件创建: case_id={} service={}", case_id, service)
            return {
                "case_id": case_id,
                "status": (result or {}).get("status", "created"),
                "service": (result or {}).get("service", service),
            }

        if not self._stub_allowed():
            raise WorkflowUnavailable("MCP Client 未配置，办件服务不可用")

        case_id = f"CASE_{uuid.uuid4().hex[:8].upper()}"
        output = {
            "case_id": case_id,
            "status": "stub",
            "service": service,
            "mode": "stub",
        }
        log_mcp_call(
            server_name="workflow_server",
            tool_name="create_case",
            input_args={"user_id": user_id, "service": service},
            output_result=output,
            latency_ms=0.0,
            status="stub",
        )
        logger.warning("办件使用 stub: case_id={} service={}", case_id, service)
        return output

    async def query_status(self, case_id: str) -> dict[str, Any]:
        """
        查询办件状态。

        Args:
            case_id: 办件 ID

        Returns:
            {case_id: str, status: str, progress: str}
        """
        if self._mcp_client is not None:
            result = await self._mcp_client.call_tool(
                "workflow_server",
                "query_status",
                {"case_id": case_id},
            )
            return {
                "case_id": (result or {}).get("case_id", case_id),
                "status": (result or {}).get("status", ""),
                "progress": (result or {}).get("progress", ""),
            }

        if not self._stub_allowed():
            raise WorkflowUnavailable("MCP Client 未配置，无法查询办件")

        output = {
            "case_id": case_id,
            "status": "stub",
            "progress": "stub 模式，未查询真实办件",
            "mode": "stub",
        }
        log_mcp_call(
            server_name="workflow_server",
            tool_name="query_status",
            input_args={"case_id": case_id},
            output_result=output,
            latency_ms=0.0,
            status="stub",
        )
        return output

    async def process(self, state: AgentState) -> AgentState:
        """
        LangGraph 节点接口。

        Args:
            state: 当前 AgentState

        Returns:
            更新后的 AgentState（含 case_id 和 workflow_result）
        """
        user_id = state.get("user_id", "default_user")
        intent = state.get("intent", "business_license")
        try:
            result = await self.create_case(
                user_id=user_id,
                service=intent,
                tenant_id=state.get("tenant_id", ""),
                trace_id=state.get("trace_id", ""),
            )
        except WorkflowUnavailable as exc:
            logger.error("Workflow 失败: {}", exc)
            return {
                **state,
                "case_id": "",
                "workflow_result": {
                    "case_id": "",
                    "service": intent,
                    "status": "failed",
                    "error": str(exc),
                },
            }

        case_id = result.get("case_id", "")
        workflow_result = {
            "case_id": case_id,
            "service": intent,
            "status": result.get("status", "created"),
        }
        if result.get("mode"):
            workflow_result["mode"] = result["mode"]
        return {
            **state,
            "case_id": case_id,
            "workflow_result": workflow_result,
        }
