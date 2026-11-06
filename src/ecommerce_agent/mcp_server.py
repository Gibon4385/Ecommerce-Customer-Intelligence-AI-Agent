from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ecommerce_agent.cli import build_runtime
from ecommerce_agent.tools.catalog import TOOL_SPECS

server = Server("ecommerce-customer-intelligence")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
        )
        for spec in TOOL_SPECS.values()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    identities, gateway, traces = build_runtime()
    user_id = os.environ.get("ECOMMERCE_AGENT_USER")
    if not user_id:
        raise ValueError("ECOMMERCE_AGENT_USER must name a trusted dev profile")
    identity = identities.resolve(user_id, channel="mcp")
    trace_id = traces.new_trace_id()
    traces.record(
        "request",
        trace_id,
        user_id=identity.user_id,
        role=identity.role,
        channel=identity.channel,
        input=f"MCP tool: {name}",
    )
    result = gateway.call(name, arguments, identity=identity, trace_id=trace_id)
    traces.record("response", trace_id, status="success")
    payload = {"trace_id": trace_id, "result": result}
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


async def run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

