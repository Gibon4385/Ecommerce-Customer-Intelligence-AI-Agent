from __future__ import annotations

from pathlib import Path

import pytest

from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.tasks.store import (
    ApprovalError,
    ApprovalExpiredError,
    DuckDBTaskStore,
    InvalidTransitionError,
    TaskError,
    TaskNotFoundError,
)


def identity(user: str, role: str) -> Identity:
    return Identity(user_id=user, role=role, data_scope="test", channel="test")


@pytest.fixture
def store(tmp_path: Path) -> DuckDBTaskStore:
    return DuckDBTaskStore(tmp_path / "tasks.duckdb")


def create(store: DuckDBTaskStore, requester: Identity, key: str = "key-1"):
    return store.create_task(
        identity=requester,
        task_type="send_edm",
        target_summary="Dormant customers",
        idempotency_key=key,
        trace_id="trace-1",
    )


def test_migration_create_and_idempotent_retry(store: DuckDBTaskStore) -> None:
    requester = identity("marketing_01", "Marketing")
    first = create(store, requester)
    second = create(store, requester)
    assert first["task_id"] == second["task_id"]
    assert first["status"] == "draft"
    assert len(store.list(identity=requester)) == 1


def test_idempotency_conflict_is_rejected(store: DuckDBTaskStore) -> None:
    create(store, identity("marketing_01", "Marketing"))
    with pytest.raises(TaskError, match="conflicts"):
        create(store, identity("marketing_02", "Marketing"))


def test_valid_state_machine_and_execution_timestamp(store: DuckDBTaskStore) -> None:
    requester = identity("marketing_01", "Marketing")
    task = create(store, requester)
    pending = store.submit(task["task_id"], identity=requester)
    assert pending["status"] == "pending_approval"
    approved = store.approve(
        task["task_id"], identity=identity("marketing_02", "Marketing")
    )
    assert approved["approved_by"] == "marketing_02"
    executed = store.transition(task["task_id"], "executed", identity=requester)
    assert executed["status"] == "executed" and executed["executed_at"] is not None
    with pytest.raises(InvalidTransitionError):
        store.transition(task["task_id"], "draft", identity=requester)


def test_self_approval_and_wrong_role_are_rejected(store: DuckDBTaskStore) -> None:
    requester = identity("marketing_01", "Marketing")
    task = create(store, requester)
    store.submit(task["task_id"], identity=requester)
    with pytest.raises(ApprovalError, match="own task"):
        store.approve(task["task_id"], identity=requester)
    with pytest.raises(ApprovalError, match="cannot approve"):
        store.approve(task["task_id"], identity=identity("support_02", "Support"))


def test_visibility_scope_and_admin_ops_access(store: DuckDBTaskStore) -> None:
    task = create(store, identity("marketing_01", "Marketing"))
    with pytest.raises(ApprovalError, match="visibility"):
        store.get(task["task_id"], identity=identity("support_01", "Support"))
    assert store.get(task["task_id"], identity=identity("ops_01", "Ops"))
    assert store.get(task["task_id"], identity=identity("admin_01", "Admin"))
    assert store.list(identity=identity("support_01", "Support")) == []


def test_missing_and_invalid_transitions(store: DuckDBTaskStore) -> None:
    with pytest.raises(TaskNotFoundError):
        store.approve("missing", identity=identity("admin_01", "Admin"))
    requester = identity("marketing_01", "Marketing")
    task = create(store, requester)
    with pytest.raises(InvalidTransitionError):
        store.transition(task["task_id"], "executed", identity=requester)


def test_empty_fields_outsider_transition_and_expired_approval(
    store: DuckDBTaskStore,
) -> None:
    requester = identity("marketing_01", "Marketing")
    with pytest.raises(TaskError, match="empty"):
        store.create_task(
            identity=requester,
            task_type="",
            target_summary="target",
            idempotency_key="empty",
            trace_id="trace",
        )
    task = create(store, requester, key="expiry-key")
    with pytest.raises(ApprovalError, match="requester"):
        store.submit(task["task_id"], identity=identity("marketing_02", "Marketing"))
    store.submit(task["task_id"], identity=requester)
    store.approve(
        task["task_id"],
        identity=identity("marketing_02", "Marketing"),
        approval_ttl_minutes=-1,
    )
    with pytest.raises(ApprovalExpiredError):
        store.transition(task["task_id"], "executed", identity=requester)

