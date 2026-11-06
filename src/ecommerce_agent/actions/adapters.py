from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb


class AdapterError(RuntimeError):
    pass


class AdapterTimeoutError(AdapterError):
    pass


class AdapterPartialFailureError(AdapterError):
    def __init__(self, external_ref: str):
        self.external_ref = external_ref
        super().__init__("mock adapter reported a partial failure")


class MockExternalAdapter:
    """Persistent mock whose idempotency behavior survives CLI restarts."""

    def __init__(
        self,
        path: Path,
        *,
        artifact_dir: Path,
        outcomes: list[str] | None = None,
    ):
        self.path = path
        self.artifact_dir = artifact_dir
        self.outcomes = list(outcomes or [])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.path)) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS mock_external_effects (
                    idempotency_key VARCHAR PRIMARY KEY,
                    action_type VARCHAR NOT NULL,
                    payload_hash VARCHAR NOT NULL,
                    state VARCHAR NOT NULL,
                    external_ref VARCHAR NOT NULL
                )"""
            )

    def execute(
        self, action_type: str, payload: dict[str, Any], *, idempotency_key: str
    ) -> str:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        payload_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with duckdb.connect(str(self.path)) as connection:
            existing = connection.execute(
                """SELECT action_type, payload_hash, state, external_ref
                FROM mock_external_effects WHERE idempotency_key=?""",
                [idempotency_key],
            ).fetchone()
            if existing:
                if existing[0] != action_type or existing[1] != payload_hash:
                    raise AdapterError("idempotency key conflicts with another external action")
                if existing[2] == "completed":
                    return existing[3]
                external_ref = existing[3]
                connection.execute(
                    """UPDATE mock_external_effects SET state='completed'
                    WHERE idempotency_key=?""",
                    [idempotency_key],
                )
                self._write_artifact(external_ref, action_type, payload)
                return external_ref

            outcome = self.outcomes.pop(0) if self.outcomes else "success"
            if outcome == "timeout":
                raise AdapterTimeoutError("mock external service timed out")
            external_ref = f"mock://{action_type}/{payload_hash[:16]}"
            state = "partial" if outcome == "partial" else "completed"
            connection.execute(
                "INSERT INTO mock_external_effects VALUES (?, ?, ?, ?, ?)",
                [idempotency_key, action_type, payload_hash, state, external_ref],
            )
            if outcome == "partial":
                raise AdapterPartialFailureError(external_ref)
            self._write_artifact(external_ref, action_type, payload)
            return external_ref

    def effect_count(self, idempotency_key: str) -> int:
        with duckdb.connect(str(self.path), read_only=True) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM mock_external_effects WHERE idempotency_key=?",
                [idempotency_key],
            ).fetchone()
        assert row is not None
        return row[0]

    def _write_artifact(
        self, external_ref: str, action_type: str, payload: dict[str, Any]
    ) -> None:
        name = external_ref.rsplit("/", 1)[-1]
        path = self.artifact_dir / f"{action_type}-{name}.json"
        path.write_text(
            json.dumps(
                {"external_ref": external_ref, "action_type": action_type, "payload": payload},
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
