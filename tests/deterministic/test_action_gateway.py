from __future__ import annotations

from pathlib import Path

import pytest

from ecommerce_agent.actions.adapters import MockExternalAdapter
from ecommerce_agent.actions.service import ActionService
from ecommerce_agent.auth.identity import DevIdentityProvider
from ecommerce_agent.data.repository import CsvMartRepository
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.tasks.store import DuckDBTaskStore
from ecommerce_agent.tools.gateway import ToolAuthorizationError, ToolGateway
from ecommerce_agent.tools.query import QueryTools

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def action_gateway(tmp_path: Path):
    traces = JsonlTraceStore(tmp_path / "traces.jsonl")
    store = DuckDBTaskStore(tmp_path / "tasks.duckdb")
    adapter = MockExternalAdapter(
        tmp_path / "external.duckdb", artifact_dir=tmp_path / "artifacts"
    )
    service = ActionService(store, adapter, traces)
    tools = QueryTools(
        CsvMartRepository(ROOT / "data", ROOT / "data/schema.yml"),
        task_store=store,
        action_service=service,
    )
    gateway = ToolGateway(tools, ROOT / "configs/rbac.yaml", traces)
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    return gateway, identities, traces, adapter


def test_public_action_tools_are_dry_run_then_approved_and_executed(action_gateway) -> None:
    gateway, identities, traces, adapter = action_gateway
    requester = identities.resolve("pm_01")
    prepared = gateway.call(
        "create_product_issue",
        {
            "product_id": "P000010",
            "evidence": "Risk review count increased",
            "priority": "high",
            "idempotency_key": "gateway-issue-1",
        },
        identity=requester,
        trace_id="prepare",
    )["data"]
    task_id = prepared["task"]["task_id"]
    assert prepared["preview"]["executable"] is False
    assert prepared["task"]["status"] == "pending_approval"
    gateway.call(
        "approve_task",
        {"task_id": task_id},
        identity=identities.resolve("pm_approver"),
        trace_id="approve",
    )
    executed = gateway.call(
        "execute_task",
        {"task_id": task_id},
        identity=requester,
        trace_id="execute",
    )["data"]
    assert executed["status"] == "executed"
    assert adapter.effect_count("gateway-issue-1") == 1
    assert traces.get("prepare")[1]["event_type"] == "action_preview"


def test_support_cannot_access_action_tools(action_gateway) -> None:
    gateway, identities, _, adapter = action_gateway
    with pytest.raises(ToolAuthorizationError):
        gateway.call(
            "send_edm",
            {
                "draft_id": "not-visible",
                "recipient_count": 1,
                "discount_pct": 0,
                "idempotency_key": "forbidden",
            },
            identity=identities.resolve("support_01"),
            trace_id="forbidden",
        )
    assert adapter.effect_count("forbidden") == 0


def test_admin_wildcard_is_limited_to_catalogued_tools(action_gateway) -> None:
    gateway, identities, _, _ = action_gateway
    allowed = gateway.allowed_tool_names(identities.resolve("admin_01"))
    assert "prepare_product_issue" not in allowed
    assert "repository" not in allowed
    assert "create_product_issue" in allowed


def test_marketing_edm_and_report_public_names_only_create_previews(action_gateway) -> None:
    gateway, identities, _, adapter = action_gateway
    marketing = identities.resolve("marketing_01")
    draft = gateway.call(
        "draft_retention_edm",
        {
            "segment": "Dormant High-Value Customer",
            "goal": "Win back",
            "subject": "Return offer",
            "idempotency_key": "gateway-draft",
        },
        identity=marketing,
        trace_id="draft",
    )["data"]
    send = gateway.call(
        "send_edm",
        {
            "draft_id": draft["task"]["task_id"],
            "recipient_count": 10,
            "discount_pct": 5,
            "idempotency_key": "gateway-send",
        },
        identity=marketing,
        trace_id="send",
    )["data"]
    report = gateway.call(
        "generate_report",
        {
            "report_type": "campaign",
            "markdown": "# Campaign preview",
            "idempotency_key": "gateway-report",
        },
        identity=marketing,
        trace_id="report",
    )["data"]
    assert send["task"]["status"] == "pending_approval"
    assert report["task"]["status"] == "pending_approval"
    assert adapter.effect_count("gateway-send") == 0
    assert adapter.effect_count("gateway-report") == 0
