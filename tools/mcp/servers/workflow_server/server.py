"""
mcp.servers.workflow_server.server - Workflow MCP Server: serve create_case and query_status

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement Workflow MCP Server with FastAPI
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from tools.mcp.schema import ToolCallRequest, ToolCallResponse
from tools.mcp.servers.workflow_server.tools import create_case, query_status
from tools.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="Workflow MCP Server",
    version="0.2.0",
    description="流程执行 MCP Server — 提供 create_case 和 query_status 能力",
)


@app.get("/health")
async def health():
    return {"status": "healthy", "server": "workflow_server", "port": 12303}


@app.post("/tools/list")
async def list_tools():
    from tools.mcp.schema import TOOL_REGISTRY
    return {"server_name": "workflow_server", "tools": TOOL_REGISTRY.get("workflow_server", [])}


@app.post("/tools/call")
async def call_tool(request: ToolCallRequest):
    tool_name = request.tool_name
    args = request.arguments

    logger.info("Workflow Server: tool={} trace={}", tool_name, request.trace_id)

    try:
        if tool_name == "create_case":
            result = await create_case(
                user_id=args.get("user_id", ""),
                service=args.get("service", ""),
                materials=args.get("materials"),
            )
            return ToolCallResponse(
                success=True,
                result=result.model_dump(),
                server_name="workflow_server",
                tool_name=tool_name,
            )

        elif tool_name == "query_status":
            result = await query_status(case_id=args.get("case_id", ""))
            return ToolCallResponse(
                success=True,
                result=result.model_dump(),
                server_name="workflow_server",
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
            server_name="workflow_server",
            tool_name=tool_name,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=12303, log_level="info")
