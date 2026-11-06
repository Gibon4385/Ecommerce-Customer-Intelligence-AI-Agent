from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ecommerce_agent.agent.orchestrator import QUERY_TOOL_NAMES
from ecommerce_agent.auth.identity import DevIdentityProvider
from ecommerce_agent.data.repository import CsvMartRepository
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.tasks.store import DuckDBTaskStore
from ecommerce_agent.tools.gateway import ToolAuthorizationError, ToolGateway
from ecommerce_agent.tools.query import QueryTools

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def security_runtime(tmp_path: Path):
    traces = JsonlTraceStore(tmp_path / "traces.jsonl")
    tools = QueryTools(
        CsvMartRepository(ROOT / "data", ROOT / "data/schema.yml"),
        DuckDBTaskStore(tmp_path / "tasks.duckdb"),
    )
    gateway = ToolGateway(tools, ROOT / "configs/rbac.yaml", traces)
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    return gateway, identities, traces


def test_every_role_has_explicit_tool_allow_deny_matrix(security_runtime) -> None:
    gateway, identities, traces = security_runtime
    config = yaml.safe_load((ROOT / "configs/rbac.yaml").read_text(encoding="utf-8"))["roles"]
    users = {
        "Support": "support_01",
        "PM": "pm_01",
        "Marketing": "marketing_01",
        "Ops": "ops_01",
        "Admin": "admin_01",
    }
    for role, user in users.items():
        identity = identities.resolve(user)
        expected = set(QUERY_TOOL_NAMES if "*" in config[role]["tools"] else config[role]["tools"])
        assert set(gateway.allowed_tool_names(identity)) & set(QUERY_TOOL_NAMES) == expected
        for denied_tool in set(QUERY_TOOL_NAMES) - expected:
            with pytest.raises(ToolAuthorizationError):
                gateway.call(denied_tool, {}, identity=identity, trace_id=traces.new_trace_id())


@pytest.mark.parametrize(
    ("user", "tool", "arguments"),
    [
        ("support_01", "get_data_freshness", {}),
        ("pm_01", "get_model_feature_importance", {}),
        ("marketing_01", "list_priority_actions", {"limit": 1}),
        ("ops_01", "get_daily_kpi", {"limit": 1}),
        ("admin_01", "get_data_freshness", {}),
    ],
)
def test_each_role_has_an_allowed_execution_example(
    security_runtime, user: str, tool: str, arguments: dict
) -> None:
    gateway, identities, traces = security_runtime
    result = gateway.call(
        tool, arguments, identity=identities.resolve(user), trace_id=traces.new_trace_id()
    )
    assert "data" in result


def test_table_matrix_is_mart_only_and_complete_for_every_role() -> None:
    roles = yaml.safe_load((ROOT / "configs/rbac.yaml").read_text(encoding="utf-8"))["roles"]
    assert set(roles) == {"Support", "PM", "Marketing", "Ops", "Admin"}
    for role in roles.values():
        assert role["tables"]
        assert all(
            table == "*" or table.startswith(("mart_", "agent_task_log"))
            for table in role["tables"]
        )


def test_support_single_customer_scope_rejects_batch_identifiers(security_runtime) -> None:
    gateway, identities, traces = security_runtime
    support = identities.resolve("support_01")
    with pytest.raises(ToolAuthorizationError, match="single_customer"):
        gateway.call(
            "get_customer_profile",
            {"user_id": ["U000001", "U000002"]},
            identity=support,
            trace_id=traces.new_trace_id(),
        )


def test_role_limits_are_enforced_before_tool_execution(security_runtime) -> None:
    gateway, identities, traces = security_runtime
    cases = [
        ("support_01", "list_tasks", 21),
        ("pm_01", "get_daily_kpi", 367),
        ("marketing_01", "list_priority_actions", 101),
        ("ops_01", "get_conversion_funnel", 1001),
    ]
    for user, tool, limit in cases:
        with pytest.raises(ToolAuthorizationError, match="limit"):
            gateway.call(
                tool,
                {"limit": limit},
                identity=identities.resolve(user),
                trace_id=traces.new_trace_id(),
            )


def test_rag_top_k_role_limit_is_enforced(security_runtime) -> None:
    gateway, identities, traces = security_runtime
    with pytest.raises(ToolAuthorizationError, match="limit"):
        gateway.call(
            "search_knowledge",
            {"query": "policy", "top_k": 6},
            identity=identities.resolve("support_01"),
            trace_id=traces.new_trace_id(),
        )
