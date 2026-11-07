from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ecommerce_agent.cli import build_runtime
from ecommerce_agent.observability.tracing import redact_value, redacted_content_record
from ecommerce_agent.tools.catalog import TOOL_SPECS

server = Server("ecommerce-customer-intelligence")


@server.list_tools()
async def list_tools() -> list[Tool]:
    identities, gateway, _ = build_runtime()
    user_id = os.environ.get("ECOMMERCE_AGENT_USER")
    if not user_id:
        raise ValueError("ECOMMERCE_AGENT_USER must name a trusted dev profile")
    identity = identities.resolve(user_id, channel="mcp")
    allowed = set(gateway.allowed_tool_names(identity))
    return [
        Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
        )
        for spec in TOOL_SPECS.values()
        if spec.name in allowed
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    identities, gateway, traces = build_runtime()
    trace_id = traces.new_trace_id()
    started = time.monotonic()
    traces.record("interaction_started", trace_id, channel="mcp", request_type="direct_tool")
    user_id = os.environ.get("ECOMMERCE_AGENT_USER")
    if not user_id:
        traces.record("interaction_failed", trace_id, error_type="IdentityError")
        raise ValueError("ECOMMERCE_AGENT_USER must name a trusted dev profile")
    identity = identities.resolve(user_id, channel="mcp")
    traces.record(
        "request",
        trace_id,
        user_id=identity.user_id,
        role=identity.role,
        channel=identity.channel,
        input=f"MCP tool: {name}",
        arguments=arguments,
    )
    try:
        result = gateway.call(name, arguments, identity=identity, trace_id=trace_id)
        payload = {"trace_id": trace_id, "result": result}
        rendered = json.dumps(payload, ensure_ascii=False, default=str)
        traces.record(
            "response",
            trace_id,
            status="success",
            output=redacted_content_record(
                json.dumps(redact_value(payload), ensure_ascii=False, default=str)
            ),
        )
        traces.record(
            "interaction_completed",
            trace_id,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        return [TextContent(type="text", text=rendered)]
    except Exception as exc:
        traces.record("response", trace_id, status="failed", error_type=type(exc).__name__)
        traces.record(
            "interaction_failed",
            trace_id,
            error_type=type(exc).__name__,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        raise


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
