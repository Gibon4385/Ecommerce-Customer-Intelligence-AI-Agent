from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from ecommerce_agent.actions.adapters import (
    AdapterError,
    AdapterPartialFailureError,
    AdapterTimeoutError,
    MockExternalAdapter,
)
from ecommerce_agent.actions.service import (
    ActionService,
    ActionValidationError,
    FrequencyLimitError,
)
from ecommerce_agent.auth.identity import DevIdentityProvider, Identity
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.tasks.store import ApprovalError, ApprovalExpiredError, DuckDBTaskStore

ROOT = Path(__file__).resolve().parents[2]


def _identity(user_id: str, role: str) -> Identity:
    return Identity(user_id, role, "test", "test")


@pytest.fixture
def action_runtime(tmp_path: Path):
    store = DuckDBTaskStore(tmp_path / "tasks.duckdb")
    adapter = MockExternalAdapter(
        tmp_path / "external.duckdb", artifact_dir=tmp_path / "artifacts"
    )
    traces = JsonlTraceStore(tmp_path / "traces.jsonl")
    service = ActionService(store, adapter, traces)
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    return service, store, adapter, traces, identities


def _draft(service: ActionService, identity: Identity, key: str = "draft-1") -> dict:
    return service.draft_retention_edm(
        segment="Dormant High-Value Customer",
        goal="Win back",
        subject="We miss you",
        identity=identity,
        idempotency_key=key,
        trace_id=f"trace-{key}",
    )


def _prepare_edm(
    service: ActionService,
    identity: Identity,
    *,
    draft_key: str = "draft-1",
    send_key: str = "send-1",
) -> dict:
    draft = _draft(service, identity, draft_key)
    return service.prepare_send_edm(
        draft_id=draft["task"]["task_id"],
        recipient_count=25,
        discount_pct=10,
        identity=identity,
        idempotency_key=send_key,
        trace_id=f"trace-{send_key}",
    )


def test_dry_run_is_non_executable_and_requires_independent_approval(action_runtime) -> None:
    service, store, _, _, identities = action_runtime
    requester = identities.resolve("marketing_01")
    prepared = _prepare_edm(service, requester)
    task = prepared["task"]
    assert task["status"] == "pending_approval"
    assert prepared["preview"]["executable"] is False
    with pytest.raises(ApprovalError, match="approved"):
        service.execute_task(task["task_id"], identity=requester, trace_id="execute-1")
    with pytest.raises(ApprovalError, match="own task"):
        service.approve_task(task["task_id"], identity=requester, trace_id="approve-self")
    approved = service.approve_task(
        task["task_id"],
        identity=identities.resolve("marketing_approver"),
        trace_id="approve-2",
    )
    assert approved["status"] == "approved"
    assert approved["approval_expires_at"] > approved["approved_at"]
    assert store.get_payload(task["task_id"])["preview"] == prepared["preview"]


def test_wrong_approver_and_wrong_executor_cannot_cause_side_effect(action_runtime) -> None:
    service, _, adapter, _, identities = action_runtime
    requester = identities.resolve("marketing_01")
    task = _prepare_edm(service, requester, send_key="send-wrong")["task"]
    with pytest.raises(ApprovalError, match="cannot approve"):
        service.approve_task(
            task["task_id"], identity=identities.resolve("pm_01"), trace_id="wrong-approve"
        )
    service.approve_task(
        task["task_id"],
        identity=identities.resolve("marketing_approver"),
        trace_id="right-approve",
    )
    with pytest.raises(ApprovalError, match="requester"):
        service.execute_task(
            task["task_id"], identity=identities.resolve("ops_01"), trace_id="wrong-exec"
        )
    assert adapter.effect_count("send-wrong") == 0


def test_expired_approval_is_rejected_before_adapter(action_runtime) -> None:
    service, store, adapter, _, identities = action_runtime
    requester = identities.resolve("marketing_01")
    task = _prepare_edm(service, requester, send_key="send-expired")["task"]
    store.approve(
        task["task_id"],
        identity=identities.resolve("marketing_approver"),
        approval_ttl_minutes=-1,
    )
    with pytest.raises(ApprovalExpiredError):
        service.execute_task(task["task_id"], identity=requester, trace_id="expired")
    assert adapter.effect_count("send-expired") == 0


def test_success_and_replay_have_one_persistent_side_effect(action_runtime) -> None:
    service, store, adapter, _, identities = action_runtime
    requester = identities.resolve("pm_01")
    prepared = service.prepare_product_issue(
        product_id="P000001",
        evidence="Rating declined with 12 risk reviews",
        priority="high",
        identity=requester,
        idempotency_key="issue-1",
        trace_id="prepare-issue",
    )
    task_id = prepared["task"]["task_id"]
    service.approve_task(
        task_id, identity=identities.resolve("pm_approver"), trace_id="approve-issue"
    )
    first = service.execute_task(task_id, identity=requester, trace_id="execute-issue")
    second = service.execute_task(task_id, identity=requester, trace_id="replay-issue")
    assert first["external_ref"] == second["external_ref"]
    assert adapter.effect_count("issue-1") == 1
    assert store.get(task_id, identity=requester)["attempt_count"] == 1


def test_duplicate_open_product_issue_is_blocked(action_runtime) -> None:
    service, _, _, _, identities = action_runtime
    requester = identities.resolve("pm_01")
    arguments = {
        "product_id": "P000002",
        "evidence": "Repeated battery complaints",
        "priority": "critical",
        "identity": requester,
        "trace_id": "issue-duplicate",
    }
    first = service.prepare_product_issue(idempotency_key="issue-a", **arguments)
    retry = service.prepare_product_issue(idempotency_key="issue-a", **arguments)
    assert first["task"]["task_id"] == retry["task"]["task_id"]
    with pytest.raises(ActionValidationError, match="already exists"):
        service.prepare_product_issue(idempotency_key="issue-b", **arguments)


@pytest.mark.parametrize(
    ("outcome", "error_type"),
    [("timeout", AdapterTimeoutError), ("partial", AdapterPartialFailureError)],
)
def test_retryable_adapter_failures_succeed_without_duplicate_effect(
    tmp_path: Path, outcome: str, error_type: type[Exception]
) -> None:
    store = DuckDBTaskStore(tmp_path / "tasks.duckdb")
    adapter = MockExternalAdapter(
        tmp_path / "external.duckdb",
        artifact_dir=tmp_path / "artifacts",
        outcomes=[outcome],
    )
    traces = JsonlTraceStore(tmp_path / "traces.jsonl")
    service = ActionService(store, adapter, traces)
    requester = _identity("pm_01", "PM")
    prepared = service.prepare_product_issue(
        product_id="P000003",
        evidence="Known evidence",
        priority="high",
        identity=requester,
        idempotency_key=f"issue-{outcome}",
        trace_id="prepare",
    )
    task_id = prepared["task"]["task_id"]
    service.approve_task(
        task_id, identity=_identity("pm_02", "PM"), trace_id="approve"
    )
    with pytest.raises(error_type):
        service.execute_task(task_id, identity=requester, trace_id="first")
    assert store.get(task_id, identity=requester)["status"] == "approved"
    completed = service.execute_task(task_id, identity=requester, trace_id="retry")
    assert completed["status"] == "executed"
    assert adapter.effect_count(f"issue-{outcome}") == 1
    assert completed["attempt_count"] == 2


def test_send_frequency_limit_is_two_per_segment_in_seven_days(action_runtime) -> None:
    service, _, adapter, _, identities = action_runtime
    requester = identities.resolve("marketing_01")
    approver = identities.resolve("marketing_approver")
    for index in range(2):
        task = _prepare_edm(
            service,
            requester,
            draft_key=f"draft-frequency-{index}",
            send_key=f"send-frequency-{index}",
        )["task"]
        service.approve_task(task["task_id"], identity=approver, trace_id=f"approve-{index}")
        service.execute_task(task["task_id"], identity=requester, trace_id=f"execute-{index}")
    third = _prepare_edm(
        service,
        requester,
        draft_key="draft-frequency-3",
        send_key="send-frequency-3",
    )["task"]
    service.approve_task(third["task_id"], identity=approver, trace_id="approve-3")
    with pytest.raises(FrequencyLimitError):
        service.execute_task(third["task_id"], identity=requester, trace_id="execute-3")
    assert adapter.effect_count("send-frequency-3") == 0


def test_report_preview_execute_and_audit_are_reconstructable(action_runtime) -> None:
    service, store, _, traces, identities = action_runtime
    requester = identities.resolve("ops_01")
    prepared = service.prepare_report(
        report_type="daily",
        markdown="# Daily report\nCompleted-only revenue.",
        identity=requester,
        idempotency_key="report-1",
        trace_id="prepare-report",
    )
    task_id = prepared["task"]["task_id"]
    service.approve_task(
        task_id, identity=identities.resolve("admin_01"), trace_id="approve-report"
    )
    service.execute_task(task_id, identity=requester, trace_id="execute-report")
    with duckdb.connect(str(store.path), read_only=True) as connection:
        attempts = connection.execute(
            "SELECT outcome, trace_id FROM agent_task_attempts WHERE task_id=?", [task_id]
        ).fetchall()
    assert attempts == [("success", "execute-report")]
    assert traces.get("prepare-report")[0]["event_type"] == "action_preview"
    assert traces.get("approve-report")[0]["event_type"] == "action_approval"
    assert traces.get("execute-report")[-1]["event_type"] == "action_execution"


def test_action_input_validation_and_missing_task(action_runtime) -> None:
    service, _, _, _, identities = action_runtime
    marketing = identities.resolve("marketing_01")
    pm = identities.resolve("pm_01")
    with pytest.raises(ActionValidationError, match="required"):
        service.draft_retention_edm(
            segment="",
            goal="goal",
            subject="subject",
            identity=marketing,
            idempotency_key="invalid-draft",
            trace_id="invalid",
        )
    draft = _draft(service, marketing, "validation-draft")
    for recipients, discount in ((0, 10), (10, 21)):
        with pytest.raises(ActionValidationError):
            service.prepare_send_edm(
                draft_id=draft["task"]["task_id"],
                recipient_count=recipients,
                discount_pct=discount,
                identity=marketing,
                idempotency_key=f"invalid-{recipients}-{discount}",
                trace_id="invalid",
            )
    with pytest.raises(ActionValidationError, match="required"):
        service.prepare_product_issue(
            product_id="",
            evidence="",
            priority="high",
            identity=pm,
            idempotency_key="invalid-issue",
            trace_id="invalid",
        )
    with pytest.raises(ActionValidationError, match="priority"):
        service.prepare_product_issue(
            product_id="P1",
            evidence="evidence",
            priority="urgent",
            identity=pm,
            idempotency_key="invalid-priority",
            trace_id="invalid",
        )
    with pytest.raises(ActionValidationError, match="report"):
        service.prepare_report(
            report_type="unknown",
            markdown="",
            identity=pm,
            idempotency_key="invalid-report",
            trace_id="invalid",
        )
    with pytest.raises(ActionValidationError, match="not found"):
        service.execute_task("missing", identity=pm, trace_id="missing")


def test_action_payload_idempotency_conflict_is_rejected(action_runtime) -> None:
    service, _, _, _, identities = action_runtime
    marketing = identities.resolve("marketing_01")
    _draft(service, marketing, "same-draft")
    with pytest.raises(ActionValidationError, match="different"):
        service.draft_retention_edm(
            segment="Another segment",
            goal="Different",
            subject="Different",
            identity=marketing,
            idempotency_key="same-draft",
            trace_id="conflict",
        )
    pm = identities.resolve("pm_01")
    service.prepare_product_issue(
        product_id="P000020",
        evidence="Evidence A",
        priority="high",
        identity=pm,
        idempotency_key="same-issue",
        trace_id="first",
    )
    with pytest.raises(ActionValidationError, match="different"):
        service.prepare_product_issue(
            product_id="P000020",
            evidence="Evidence B",
            priority="high",
            identity=pm,
            idempotency_key="same-issue",
            trace_id="conflict",
        )


def test_mock_adapter_replay_and_conflicting_key(tmp_path: Path) -> None:
    adapter = MockExternalAdapter(
        tmp_path / "external.duckdb", artifact_dir=tmp_path / "artifacts"
    )
    first = adapter.execute("report", {"value": 1}, idempotency_key="adapter-key")
    assert adapter.execute("report", {"value": 1}, idempotency_key="adapter-key") == first
    with pytest.raises(AdapterError, match="conflicts"):
        adapter.execute("report", {"value": 2}, idempotency_key="adapter-key")
