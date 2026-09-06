"""
mcp.servers.policy_server.server - Policy MCP Server: serve search_policy and get_policy_detail

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement Policy MCP Server with FastAPI, serving search_policy + get_policy_detail
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from tools.mcp.schema import (
    ToolCallRequest,
    ToolCallResponse,
    SearchPolicyInput,
    GetPolicyDetailInput,
)
from tools.mcp.servers.policy_server.tools import search_policy, get_policy_detail
from tools.logger import get_logger

logger = get_logger(__name__)

# ── FastAPI App ──
app = FastAPI(
    title="Policy MCP Server",
    version="0.2.0",
    description="政策知识检索 MCP Server — 提供 search_policy 和 get_policy_detail 能力",
)


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy", "server": "policy_server", "port": 12011}


@app.post("/tools/list")
async def list_tools():
    """返回本 Server 所有工具的 Schema 定义"""
    from tools.mcp.schema import TOOL_REGISTRY
    return {"server_name": "policy_server", "tools": TOOL_REGISTRY.get("policy_server", [])}


@app.post("/tools/call")
async def call_tool(request: ToolCallRequest):
    """
    调用工具的统一入口。

    根据 tool_name 分发到对应的处理函数。
    返回 ToolCallResponse 统一格式。
    """
    tool_name = request.tool_name
    args = request.arguments

    logger.info(
        "Policy Server: tool={} args={} trace={}",
        tool_name, args, request.trace_id,
    )

    try:
        if tool_name == "search_policy":
            search_input = SearchPolicyInput(**args)
            search_result = await search_policy(
                query=search_input.query,
                top_k=search_input.top_k,
                trace_id=request.trace_id,
            )
            return ToolCallResponse(
                success=True,
                result=search_result.model_dump(),
                server_name="policy_server",
                tool_name=tool_name,
            )

        elif tool_name == "get_policy_detail":
            detail_input = GetPolicyDetailInput(**args)
            detail_result = await get_policy_detail(
                document_id=detail_input.document_id,
            )
            return ToolCallResponse(
                success=True,
                result=detail_result.model_dump(),
                server_name="policy_server",
                tool_name=tool_name,
            )

        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Tool call failed: {} - {}", tool_name, e)
        return ToolCallResponse(
            success=False,
            error=str(e),
            server_name="policy_server",
            tool_name=tool_name,
        )


# ============================================================
# 直接运行入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=12011, log_level="info")
