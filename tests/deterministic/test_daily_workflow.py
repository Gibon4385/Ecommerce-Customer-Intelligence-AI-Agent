from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ecommerce_agent.actions.adapters import MockExternalAdapter
from ecommerce_agent.actions.service import ActionService
from ecommerce_agent.auth.identity import DevIdentityProvider
from ecommerce_agent.data.repository import CsvMartRepository
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.rag.store import DuckDBRagStore
from ecommerce_agent.tasks.store import DuckDBTaskStore
from ecommerce_agent.tools.gateway import ToolAuthorizationError, ToolGateway
from ecommerce_agent.tools.query import QueryTools
from ecommerce_agent.workflows import DailyOperationsWorkflow

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workflow_runtime(tmp_path: Path):
    traces = JsonlTraceStore(tmp_path / "traces.jsonl")
    task_store = DuckDBTaskStore(tmp_path / "tasks.duckdb")
    rag_store = DuckDBRagStore(tmp_path / "knowledge.duckdb")
    rag_store.rebuild_from_manifest(ROOT / "configs/rag_sources.yaml", root=ROOT)
    adapter = MockExternalAdapter(
        tmp_path / "external.duckdb", artifact_dir=tmp_path / "artifacts"
    )
    actions = ActionService(task_store, adapter, traces)
    tools = QueryTools(
        CsvMartRepository(ROOT / "data", ROOT / "data/schema.yml"),
        task_store,
        rag_store,
        actions,
    )
    gateway = ToolGateway(tools, ROOT / "configs/rbac.yaml", traces)
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    return DailyOperationsWorkflow(gateway, traces), gateway, identities, task_store, traces


@pytest.mark.parametrize("user_id", ["ops_01", "pm_01", "marketing_01"])
def test_daily_report_is_deterministic_role_authorized_and_audited(
    workflow_runtime, user_id: str
) -> None:
    workflow, gateway, identities, task_store, traces = workflow_runtime
    identity = identities.resolve(user_id)
    expected = gateway.call(
        "get_daily_kpi", {"limit": 29}, identity=identity, trace_id=f"expected-{user_id}"
    )
    result = workflow.run(identity=identity)
    latest = expected["data"][0]
    assert f"最新 completed-only 營收：{latest['revenue']}" in result.markdown
    assert f"訂單：{latest['orders']}" in result.markdown
    assert expected["data_as_of"] in result.markdown
    assert "## 資料事實" in result.markdown and "## 推論與建議檢查" in result.markdown
    assert "knowledge_base/data_dictionary/ops_marts.md#L" in result.markdown
    assert result.delayed is True and "資料延遲" in result.markdown
    task = task_store.get(result.report_task_id, identity=identity)
    assert task["task_type"] == "report" and task["status"] == "pending_approval"
    events = traces.get(result.trace_id)
    assert events[0]["event_type"] == "interaction_started"
    assert events[-2]["event_type"] == "workflow_complete"
    assert events[-1]["event_type"] == "interaction_completed"


def test_daily_report_is_idempotent_for_same_snapshot(workflow_runtime) -> None:
    workflow, _, identities, task_store, _ = workflow_runtime
    identity = identities.resolve("ops_01")
    first = workflow.run(identity=identity)
    second = workflow.run(identity=identity)
    assert first.markdown == second.markdown
    assert first.report_task_id == second.report_task_id
    assert len(task_store.list(identity=identity)) == 1


def test_support_cannot_run_daily_report(workflow_runtime) -> None:
    workflow, _, identities, _, traces = workflow_runtime
    with pytest.raises(ToolAuthorizationError):
        workflow.run(identity=identities.resolve("support_01"))
    events = traces.recent(20)
    assert events[-1]["event_type"] == "interaction_failed"
    assert events[-1]["payload"]["error_type"] == "ToolAuthorizationError"


def test_delay_detection_handles_failed_and_fresh_data() -> None:
    assert DailyOperationsWorkflow._is_delayed(
        [{"status": "failed"}], date.today().isoformat()
    )
    assert not DailyOperationsWorkflow._is_delayed(
        [{"status": "success"}], date.today().isoformat()
    )
