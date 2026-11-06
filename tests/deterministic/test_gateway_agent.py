from __future__ import annotations

from pathlib import Path

import pytest

from ecommerce_agent.agent.llm import FakeLLMClient
from ecommerce_agent.agent.orchestrator import MinimalAgent
from ecommerce_agent.agent.prompts import PromptBundle
from ecommerce_agent.auth.identity import DevIdentityProvider
from ecommerce_agent.data.repository import CsvMartRepository
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.tools.gateway import (
    ToolAuthorizationError,
    ToolGateway,
    ToolNotFoundError,
)
from ecommerce_agent.tools.query import QueryTools

ROOT = Path(__file__).resolve().parents[2]
PROMPT = PromptBundle(version="test", system="Test system prompt")


@pytest.fixture
def runtime(tmp_path: Path):
    traces = JsonlTraceStore(tmp_path / "traces.jsonl")
    repository = CsvMartRepository(ROOT / "data", ROOT / "data/schema.yml")
    gateway = ToolGateway(QueryTools(repository), ROOT / "configs/rbac.yaml", traces)
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    return gateway, identities, traces


def test_gateway_authorizes_and_traces(runtime) -> None:
    gateway, identities, traces = runtime
    trace_id = traces.new_trace_id()
    result = gateway.call(
        "get_daily_kpi", {"limit": 2}, identity=identities.resolve("ops_01"), trace_id=trace_id
    )
    assert len(result["data"]) == 2
    assert [event["event_type"] for event in traces.get(trace_id)] == [
        "authorization",
        "tool_result",
    ]


def test_gateway_denies_role_and_unknown_tool(runtime) -> None:
    gateway, identities, traces = runtime
    with pytest.raises(ToolAuthorizationError):
        gateway.call(
            "list_priority_actions",
            {},
            identity=identities.resolve("support_01"),
            trace_id=traces.new_trace_id(),
        )


def test_gateway_records_tool_error(runtime) -> None:
    gateway, identities, traces = runtime
    trace_id = traces.new_trace_id()
    with pytest.raises(ValueError):
        gateway.call(
            "get_daily_kpi",
            {"limit": 0},
            identity=identities.resolve("ops_01"),
            trace_id=trace_id,
        )
    assert traces.get(trace_id)[-1]["event_type"] == "tool_error"


def test_gateway_enforces_role_limit_and_masks_fields(runtime) -> None:
    gateway, identities, traces = runtime
    with pytest.raises(ToolAuthorizationError, match="limit"):
        gateway.call(
            "list_tasks",
            {"limit": 21},
            identity=identities.resolve("support_01"),
            trace_id=traces.new_trace_id(),
        )
    support_trace = traces.new_trace_id()
    support = gateway.call(
        "get_customer_profile",
        {"user_id": "U000001"},
        identity=identities.resolve("support_01"),
        trace_id=support_trace,
    )["data"]
    assert "predicted_profit_90_days" not in support
    marketing = gateway.call(
        "get_customer_profile",
        {"user_id": "U000001"},
        identity=identities.resolve("marketing_01"),
        trace_id=traces.new_trace_id(),
    )["data"]
    assert "predicted_profit_90_days" in marketing
    authorization = traces.get(support_trace)[0]
    assert authorization["payload"]["arguments"]["user_id"] == "[REDACTED_IDENTIFIER]"

    with pytest.raises(ToolNotFoundError):
        gateway.call(
            "not_a_tool",
            {},
            identity=identities.resolve("admin_01"),
            trace_id=traces.new_trace_id(),
        )


def test_agent_tool_flow_preserves_trusted_identity(runtime) -> None:
    gateway, identities, traces = runtime
    llm = FakeLLMClient(
        [
            {"tool": "get_daily_kpi", "arguments": {"limit": 1}},
            {"answer": "最近一個資料日的 completed 訂單收入已查得。"},
        ]
    )
    agent = MinimalAgent(llm, gateway, traces, PROMPT)
    response = agent.run("查最近收入", identity=identities.resolve("ops_01"))
    assert "completed" in response.answer
    events = traces.get(response.trace_id)
    authorization = next(event for event in events if event["event_type"] == "authorization")
    assert authorization["payload"]["role"] == "Ops"
    assert events[0]["event_type"] == "request" and events[-1]["event_type"] == "response"
    assert events[0]["payload"]["prompt_version"] == "test"


def test_agent_direct_answer_and_failure_trace(runtime) -> None:
    gateway, identities, traces = runtime
    direct = MinimalAgent(FakeLLMClient([{"answer": "你好"}]), gateway, traces, PROMPT)
    assert direct.run("你好", identity=identities.resolve("ops_01")).answer == "你好"
    invalid = MinimalAgent(
        FakeLLMClient([{"tool": "bad", "arguments": {}}]), gateway, traces, PROMPT
    )
    with pytest.raises(ValueError):
        invalid.run("bad", identity=identities.resolve("ops_01"))


def test_agent_can_combine_two_tools(runtime) -> None:
    gateway, identities, traces = runtime
    llm = FakeLLMClient(
        [
            {
                "tools": [
                    {"name": "get_daily_kpi", "arguments": {"limit": 1}},
                    {"name": "get_data_freshness", "arguments": {}},
                ]
            },
            {"answer": "已合併 KPI 與資料更新狀態。"},
        ]
    )
    response = MinimalAgent(llm, gateway, traces, PROMPT).run(
        "收入與資料更新狀態", identity=identities.resolve("ops_01")
    )
    assert "合併" in response.answer
    assert sum(e["event_type"] == "tool_result" for e in traces.get(response.trace_id)) == 2


def test_planning_prompt_contains_exact_tool_schema(runtime) -> None:
    gateway, identities, traces = runtime
    agent = MinimalAgent(FakeLLMClient([]), gateway, traces, PROMPT)
    prompt = agent._planning_prompt("customer", identities.resolve("support_01"))
    assert '"user_id"' in prompt
    assert '"additionalProperties": false' in prompt
    assert "list_priority_actions" not in prompt

