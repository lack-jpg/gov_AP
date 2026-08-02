"""
mcp.servers.material_server.server - Material MCP Server: serve extract_entity and check_material

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement Material MCP Server with FastAPI
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from tools.mcp.schema import ToolCallRequest, ToolCallResponse
from tools.mcp.servers.material_server.tools import extract_entity, check_material
from tools.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="Material MCP Server",
    version="0.2.0",
    description="材料审核 MCP Server — 提供 extract_entity 和 check_material 能力",
)


@app.get("/health")
async def health():
    return {"status": "healthy", "server": "material_server", "port": 12302}


@app.post("/tools/list")
async def list_tools():
    from tools.mcp.schema import TOOL_REGISTRY
    return {"server_name": "material_server", "tools": TOOL_REGISTRY.get("material_server", [])}


@app.post("/tools/call")
async def call_tool(request: ToolCallRequest):
    tool_name = request.tool_name
    args = request.arguments

    logger.info("Material Server: tool={} trace={}", tool_name, request.trace_id)

    try:
        if tool_name == "extract_entity":
            field_schema_raw = args.get("field_schema")
            field_schema = field_schema_raw if isinstance(field_schema_raw, dict) else None
            result = await extract_entity(
                file_id=args.get("file_id", ""),
                field_schema=field_schema,
            )
            return ToolCallResponse(
                success=True,
                result=result.model_dump(),
                server_name="material_server",
                tool_name=tool_name,
            )

        elif tool_name == "check_material":
            result = await check_material(
                business_type=args.get("business_type", ""),
                materials=args.get("materials", []),
            )
            return ToolCallResponse(
                success=True,
                result=result.model_dump(),
                server_name="material_server",
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
            server_name="material_server",
            tool_name=tool_name,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=12302, log_level="info")
