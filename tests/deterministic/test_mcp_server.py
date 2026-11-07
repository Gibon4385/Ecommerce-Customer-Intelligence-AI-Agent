from __future__ import annotations

import json

import pytest

from ecommerce_agent import mcp_server


@pytest.mark.asyncio
async def test_mcp_lists_only_role_authorized_business_tools(monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_AGENT_USER", "ops_01")
    tools = await mcp_server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "get_daily_kpi" in by_name
    assert "search_knowledge" in by_name
    assert "send_edm" not in by_name
    assert "create_product_issue" in by_name
    assert "generate_report" in by_name
    assert "get_customer_profile" not in by_name


@pytest.mark.asyncio
async def test_mcp_call_uses_trusted_environment_identity(monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_AGENT_USER", "ops_01")
    content = await mcp_server.call_tool("get_daily_kpi", {"limit": 1})
    payload = json.loads(content[0].text)
    assert len(payload["result"]["data"]) == 1
    assert payload["trace_id"]


@pytest.mark.asyncio
async def test_mcp_requires_identity(monkeypatch) -> None:
    monkeypatch.delenv("ECOMMERCE_AGENT_USER", raising=False)
    with pytest.raises(ValueError, match="ECOMMERCE_AGENT_USER"):
        await mcp_server.call_tool("get_daily_kpi", {"limit": 1})

