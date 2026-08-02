"""
tools.mcp.start_servers - 一键启动所有 MCP Server + Gateway

Author: le
Date: 2026/7/30
Version: 0.2
Task: Launch all 3 MCP Servers + Gateway in a single process

Usage:
    python tools/mcp/start_servers.py             # 启动所有服务
    python tools/mcp/start_servers.py --no-gateway  # 只启动 MCP Servers
"""
from __future__ import annotations

import asyncio
import argparse

import uvicorn


SERVERS = [
    ("tools.mcp.servers.policy_server.server:app", 12301, "Policy"),
    ("tools.mcp.servers.material_server.server:app", 12302, "Material"),
    ("tools.mcp.servers.workflow_server.server:app", 12303, "Workflow"),
]


async def start_server(app_path: str, port: int, name: str):
    """启动单个 MCP Server"""
    config = uvicorn.Config(
        app_path,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    print(f"[{name}] Starting on port {port}...")
    await server.serve()


async def main():
    parser = argparse.ArgumentParser(description="Start MCP infrastructure")
    parser.add_argument("--no-gateway", action="store_true", help="Skip Gateway")
    args = parser.parse_args()

    tasks = []

    # ── 启动 3 个 MCP Server ──
    for app_path, port, name in SERVERS:
        tasks.append(start_server(app_path, port, name))

    # ── 启动 Gateway ──
    if not args.no_gateway:
        async def start_gateway():
            from tools.mcp.gateway import app as gateway_app
            config = uvicorn.Config(
                gateway_app,
                host="0.0.0.0",
                port=12300,
                log_level="info",
            )
            server = uvicorn.Server(config)
            print("[Gateway] Starting on port 12300...")
            await server.serve()

        tasks.append(start_gateway())

    print(f"Starting {len(tasks)} services...")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
