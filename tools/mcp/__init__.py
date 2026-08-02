"""
mcp - Model Context Protocol: standardized Agent-to-Tool communication layer

Author: le
Date: 2026/7/30
Version: 0.2
Task: MCP package initialization — exports MCPClient, MCPGateway, tool schemas
"""
from __future__ import annotations

from tools.mcp.client import MCPClient, MCPToolError, MCPToolTimeout
from tools.mcp.gateway import MCPGateway
from tools.mcp.schema import (
    TOOL_REGISTRY,
    ToolCallRequest,
    ToolCallResponse,
    SearchPolicyInput,
    SearchPolicyOutput,
    CheckMaterialInput,
    CheckMaterialOutput,
    CreateCaseInput,
    CreateCaseOutput,
    QueryStatusInput,
    QueryStatusOutput,
)

__all__ = [
    "MCPClient",
    "MCPGateway",
    "MCPToolError",
    "MCPToolTimeout",
    "TOOL_REGISTRY",
    "ToolCallRequest",
    "ToolCallResponse",
    "SearchPolicyInput",
    "SearchPolicyOutput",
    "CheckMaterialInput",
    "CheckMaterialOutput",
    "CreateCaseInput",
    "CreateCaseOutput",
    "QueryStatusInput",
    "QueryStatusOutput",
]
