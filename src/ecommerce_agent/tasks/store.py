from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from ecommerce_agent.auth.identity import Identity


class TaskError(RuntimeError):
    pass


class TaskNotFoundError(TaskError):
    pass


class InvalidTransitionError(TaskError):
    pass


class ApprovalError(TaskError):
    pass


class ApprovalExpiredError(ApprovalError):
    pass


TRANSITIONS = {
    "draft": {"pending_approval", "cancelled"},
    "pending_approval": {"approved", "cancelled"},
    "approved": {"executed", "failed", "cancelled"},
    "executed": set(),
    "failed": set(),
    "cancelled": set(),
}


def _utc_now() -> datetime:
    """Return a naive UTC value compatible with DuckDB TIMESTAMP."""
    return datetime.now(UTC).replace(tzinfo=None)


class DuckDBTaskStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.path))

    def migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_task_log (
                    task_id VARCHAR PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL,
                    requested_by VARCHAR NOT NULL,
                    requester_role VARCHAR NOT NULL,
                    task_type VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    target_summary VARCHAR NOT NULL,
                    payload_ref VARCHAR,
                    approved_by VARCHAR,
                    approved_at TIMESTAMP,
                    approval_expires_at TIMESTAMP,
                    executed_at TIMESTAMP,
                    external_ref VARCHAR,
                    idempotency_key VARCHAR NOT NULL UNIQUE,
                    trace_id VARCHAR NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error VARCHAR
                );
                CREATE TABLE IF NOT EXISTS agent_task_payloads (
                    task_id VARCHAR PRIMARY KEY,
                    payload_json VARCHAR NOT NULL,
                    preview_json VARCHAR NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_task_attempts (
                    attempt_id VARCHAR PRIMARY KEY,
                    task_id VARCHAR NOT NULL,
                    attempted_at TIMESTAMP NOT NULL,
                    actor_id VARCHAR NOT NULL,
                    outcome VARCHAR NOT NULL,
                    error_type VARCHAR,
                    external_ref VARCHAR,
                    trace_id VARCHAR NOT NULL
                )
                """
            )
            columns = {
                row[0] for row in connection.execute("DESCRIBE agent_task_log").fetchall()
            }
            additions = {
                "approval_expires_at": "TIMESTAMP",
                "attempt_count": "INTEGER DEFAULT 0",
                "last_error": "VARCHAR",
            }
            for name, data_type in additions.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE agent_task_log ADD COLUMN {name} {data_type}"
                    )

    def create_task(
        self,
        *,
        identity: Identity,
        task_type: str,
        target_summary: str,
        idempotency_key: str,
        trace_id: str,
        payload_ref: str | None = None,
    ) -> dict[str, Any]:
        if not all((task_type, target_summary, idempotency_key, trace_id)):
            raise TaskError("task fields must not be empty")
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM agent_task_log WHERE idempotency_key = ?", [idempotency_key]
            ).fetchone()
            if existing:
                columns = [item[0] for item in connection.description]
                record = dict(zip(columns, existing, strict=True))
                if record["requested_by"] != identity.user_id or record["task_type"] != task_type:
                    raise TaskError("idempotency key conflicts with another task")
                return record
            task_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO agent_task_log
                (task_id, created_at, requested_by, requester_role, task_type, status,
                 target_summary, payload_ref, idempotency_key, trace_id)
                VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)""",
                [
                    task_id,
                    _utc_now(),
                    identity.user_id,
                    identity.role,
                    task_type,
                    target_summary,
                    payload_ref,
                    idempotency_key,
                    trace_id,
                ],
            )
        created = self.get(task_id, identity=identity)
        assert created is not None
        return created

    def get(self, task_id: str, *, identity: Identity) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_task_log WHERE task_id = ?", [task_id]
            ).fetchone()
            if row is None:
                return None
            columns = [item[0] for item in connection.description]
            record = dict(zip(columns, row, strict=True))
        if identity.role not in {"Admin", "Ops"} and record["requested_by"] != identity.user_id:
            raise ApprovalError("task is outside the caller's visibility scope")
        return record

    def list(self, *, identity: Identity, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if identity.role in {"Admin", "Ops"}:
                rows = connection.execute(
                    "SELECT * FROM agent_task_log ORDER BY created_at DESC LIMIT ?", [limit]
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT * FROM agent_task_log WHERE requested_by = ?
                    ORDER BY created_at DESC LIMIT ?""",
                    [identity.user_id, limit],
                ).fetchall()
            columns = [item[0] for item in connection.description]
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def submit(self, task_id: str, *, identity: Identity) -> dict[str, Any]:
        return self._transition(task_id, "pending_approval", identity=identity)

    def approve(
        self, task_id: str, *, identity: Identity, approval_ttl_minutes: int = 30
    ) -> dict[str, Any]:
        record = self._get_unscoped(task_id)
        if record["requested_by"] == identity.user_id:
            raise ApprovalError("requester cannot approve their own task")
        allowed_roles = {
            "send_edm": {"Marketing", "Admin"},
            "audience_export": {"Marketing", "Admin"},
            "product_issue": {"PM", "Admin"},
            "report": {"Ops", "PM", "Marketing", "Admin"},
        }.get(record["task_type"], {"Admin"})
        if identity.role not in allowed_roles:
            raise ApprovalError(f"role {identity.role} cannot approve {record['task_type']}")
        return self._transition(
            task_id,
            "approved",
            identity=identity,
            approver=True,
            approval_ttl_minutes=approval_ttl_minutes,
        )

    def transition(self, task_id: str, status: str, *, identity: Identity) -> dict[str, Any]:
        return self._transition(task_id, status, identity=identity)

    def _get_unscoped(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_task_log WHERE task_id = ?", [task_id]
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(task_id)
            columns = [item[0] for item in connection.description]
        return dict(zip(columns, row, strict=True))

    def _transition(
        self,
        task_id: str,
        status: str,
        *,
        identity: Identity,
        approver: bool = False,
        approval_ttl_minutes: int = 30,
    ) -> dict[str, Any]:
        record = self._get_unscoped(task_id)
        if status not in TRANSITIONS.get(record["status"], set()):
            raise InvalidTransitionError(f"{record['status']} -> {status} is not allowed")
        if not approver and identity.role != "Admin" and record["requested_by"] != identity.user_id:
            raise ApprovalError("only the requester or Admin may transition this task")
        now = _utc_now()
        if (
            status == "executed"
            and record.get("approval_expires_at") is not None
            and now > record["approval_expires_at"]
        ):
            raise ApprovalExpiredError("approval has expired")
        approved_by = identity.user_id if status == "approved" else record["approved_by"]
        approved_at = now if status == "approved" else record["approved_at"]
        approval_expires_at = (
            now + timedelta(minutes=approval_ttl_minutes)
            if status == "approved"
            else record.get("approval_expires_at")
        )
        executed_at = now if status == "executed" else record["executed_at"]
        last_error = None if status == "approved" else record.get("last_error")
        with self._connect() as connection:
            connection.execute(
                """UPDATE agent_task_log SET status=?, approved_by=?, approved_at=?,
                approval_expires_at=?, executed_at=?, last_error=?
                WHERE task_id=?""",
                [
                    status,
                    approved_by,
                    approved_at,
                    approval_expires_at,
                    executed_at,
                    last_error,
                    task_id,
                ],
            )
        return self._get_unscoped(task_id)

    def save_payload(
        self, task_id: str, *, payload: dict[str, Any], preview: dict[str, Any]
    ) -> None:
        self._get_unscoped(task_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO agent_task_payloads VALUES (?, ?, ?)",
                [
                    task_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(preview, ensure_ascii=False, sort_keys=True),
                ],
            )

    def get_payload(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json, preview_json FROM agent_task_payloads WHERE task_id=?",
                [task_id],
            ).fetchone()
        if row is None:
            raise TaskNotFoundError(f"payload for {task_id}")
        return {"payload": json.loads(row[0]), "preview": json.loads(row[1])}

    def record_attempt(
        self,
        task_id: str,
        *,
        identity: Identity,
        outcome: str,
        trace_id: str,
        error_type: str | None = None,
        external_ref: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO agent_task_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    str(uuid.uuid4()),
                    task_id,
                    _utc_now(),
                    identity.user_id,
                    outcome,
                    error_type,
                    external_ref,
                    trace_id,
                ],
            )
            connection.execute(
                """UPDATE agent_task_log SET attempt_count=attempt_count+1, last_error=?
                WHERE task_id=?""",
                [error_type, task_id],
            )

    def set_external_ref(self, task_id: str, external_ref: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE agent_task_log SET external_ref=?, last_error=NULL WHERE task_id=?",
                [external_ref, task_id],
            )

    def count_recent_executed(self, *, task_type: str, target_summary: str, days: int) -> int:
        cutoff = _utc_now() - timedelta(days=days)
        with self._connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) FROM agent_task_log
                WHERE task_type=? AND target_summary=? AND status='executed' AND executed_at>=?""",
                [task_type, target_summary, cutoff],
            ).fetchone()
        assert row is not None
        return row[0]

    def find_active(self, *, task_type: str, target_summary: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM agent_task_log
                WHERE task_type=? AND target_summary=?
                  AND status IN ('draft', 'pending_approval', 'approved')
                ORDER BY created_at DESC LIMIT 1""",
                [task_type, target_summary],
            ).fetchone()
            if row is None:
                return None
            columns = [item[0] for item in connection.description]
        return dict(zip(columns, row, strict=True))

