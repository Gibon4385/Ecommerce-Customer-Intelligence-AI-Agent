from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ecommerce_agent.actions.adapters import (
    AdapterPartialFailureError,
    AdapterTimeoutError,
    MockExternalAdapter,
)
from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.tasks.store import (
    ApprovalError,
    ApprovalExpiredError,
    DuckDBTaskStore,
    TaskError,
    TaskNotFoundError,
)


class ActionValidationError(TaskError):
    pass


class FrequencyLimitError(TaskError):
    pass


class ActionService:
    def __init__(
        self,
        store: DuckDBTaskStore,
        adapter: MockExternalAdapter,
        traces: JsonlTraceStore,
    ):
        self.store = store
        self.adapter = adapter
        self.traces = traces

    def draft_retention_edm(
        self,
        *,
        segment: str,
        goal: str,
        subject: str,
        identity: Identity,
        idempotency_key: str,
        trace_id: str,
    ) -> dict[str, Any]:
        if not all((segment.strip(), goal.strip(), subject.strip())):
            raise ActionValidationError("segment, goal and subject are required")
        task = self.store.create_task(
            identity=identity,
            task_type="draft_edm",
            target_summary=segment,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )
        payload = {"segment": segment, "goal": goal, "subject": subject}
        preview = {**payload, "executable": False, "variants": 2}
        try:
            existing = self.store.get_payload(task["task_id"])
        except TaskNotFoundError:
            existing = None
        if existing is not None:
            if existing["payload"] != payload:
                raise ActionValidationError(
                    "idempotency key conflicts with a different action payload"
                )
            return {"task": task, "preview": existing["preview"]}
        self.store.save_payload(task["task_id"], payload=payload, preview=preview)
        self.traces.record("action_preview", trace_id, task_id=task["task_id"], action="draft_edm")
        return {"task": task, "preview": preview}

    def prepare_send_edm(
        self,
        *,
        draft_id: str,
        recipient_count: int,
        discount_pct: float,
        identity: Identity,
        idempotency_key: str,
        trace_id: str,
    ) -> dict[str, Any]:
        if not 1 <= recipient_count <= 1000:
            raise ActionValidationError("recipient_count must be between 1 and 1000")
        if not 0 <= discount_pct <= 20:
            raise ActionValidationError("discount_pct must be between 0 and 20")
        draft = self.store.get_payload(draft_id)["payload"]
        payload = {
            "draft_id": draft_id,
            "segment": draft["segment"],
            "subject": draft["subject"],
            "recipient_count": recipient_count,
            "discount_pct": discount_pct,
        }
        preview = {**payload, "executable": False, "requires_approval": True}
        return self._prepare(
            "send_edm",
            draft["segment"],
            payload,
            preview,
            identity=identity,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

    def prepare_product_issue(
        self,
        *,
        product_id: str,
        evidence: str,
        priority: str,
        identity: Identity,
        idempotency_key: str,
        trace_id: str,
    ) -> dict[str, Any]:
        if not product_id or not evidence:
            raise ActionValidationError("product_id and evidence are required")
        if priority not in {"low", "medium", "high", "critical"}:
            raise ActionValidationError("invalid priority")
        active = self.store.find_active(
            task_type="product_issue", target_summary=product_id
        )
        if active is not None and active["idempotency_key"] != idempotency_key:
            raise ActionValidationError("an active product issue already exists")
        payload = {"product_id": product_id, "evidence": evidence, "priority": priority}
        preview = {**payload, "executable": False, "requires_approval": True}
        return self._prepare(
            "product_issue",
            product_id,
            payload,
            preview,
            identity=identity,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

    def prepare_report(
        self,
        *,
        report_type: str,
        markdown: str,
        identity: Identity,
        idempotency_key: str,
        trace_id: str,
    ) -> dict[str, Any]:
        if report_type not in {"daily", "weekly", "campaign"} or not markdown.strip():
            raise ActionValidationError("invalid report type or empty markdown")
        payload = {"report_type": report_type, "markdown": markdown}
        preview = {
            "report_type": report_type,
            "character_count": len(markdown),
            "executable": False,
            "requires_approval": True,
        }
        return self._prepare(
            "report",
            report_type,
            payload,
            preview,
            identity=identity,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

    def approve_task(
        self, task_id: str, *, identity: Identity, trace_id: str
    ) -> dict[str, Any]:
        try:
            task = self.store.approve(task_id, identity=identity)
        except ApprovalError as exc:
            self.traces.record(
                "action_approval",
                trace_id,
                task_id=task_id,
                outcome="denied",
                error_type=type(exc).__name__,
            )
            raise
        self.traces.record(
            "action_approval", trace_id, task_id=task_id, outcome="approved"
        )
        return task

    def execute_task(
        self, task_id: str, *, identity: Identity, trace_id: str
    ) -> dict[str, Any]:
        task = self.store.get(task_id, identity=identity)
        if task is None:
            raise ActionValidationError("task not found")
        if task["status"] == "executed":
            self.traces.record(
                "action_execution",
                trace_id,
                task_id=task_id,
                outcome="idempotent_replay",
                external_ref=task["external_ref"],
            )
            return task
        if identity.role != "Admin" and task["requested_by"] != identity.user_id:
            self._record_denied(task_id, identity, trace_id, "ApprovalError")
            raise ApprovalError("only the requester or Admin may execute this task")
        if task["status"] != "approved":
            self._record_denied(task_id, identity, trace_id, "ApprovalError")
            raise ApprovalError("task must be approved before execution")
        if (
            task.get("approval_expires_at") is not None
            and datetime.now(UTC).replace(tzinfo=None) > task["approval_expires_at"]
        ):
            self._record_denied(task_id, identity, trace_id, "ApprovalExpiredError")
            raise ApprovalExpiredError("approval has expired")
        if (
            task["task_type"] == "send_edm"
            and self.store.count_recent_executed(
                task_type="send_edm", target_summary=task["target_summary"], days=7
            )
            >= 2
        ):
            self._record_denied(task_id, identity, trace_id, "FrequencyLimitError")
            raise FrequencyLimitError("segment reached the two sends per seven days limit")
        payload = self.store.get_payload(task_id)["payload"]
        try:
            external_ref = self.adapter.execute(
                task["task_type"], payload, idempotency_key=task["idempotency_key"]
            )
        except (AdapterTimeoutError, AdapterPartialFailureError) as exc:
            self.store.record_attempt(
                task_id,
                identity=identity,
                outcome="retryable_failure",
                error_type=type(exc).__name__,
                external_ref=getattr(exc, "external_ref", None),
                trace_id=trace_id,
            )
            self.traces.record(
                "action_execution",
                trace_id,
                task_id=task_id,
                outcome="retryable_failure",
                error_type=type(exc).__name__,
            )
            raise
        self.store.set_external_ref(task_id, external_ref)
        self.store.record_attempt(
            task_id,
            identity=identity,
            outcome="success",
            external_ref=external_ref,
            trace_id=trace_id,
        )
        executed = self.store.transition(task_id, "executed", identity=identity)
        self.traces.record(
            "action_execution",
            trace_id,
            task_id=task_id,
            outcome="success",
            external_ref=external_ref,
        )
        return executed

    def _prepare(
        self,
        task_type: str,
        target_summary: str,
        payload: dict[str, Any],
        preview: dict[str, Any],
        *,
        identity: Identity,
        idempotency_key: str,
        trace_id: str,
    ) -> dict[str, Any]:
        task = self.store.create_task(
            identity=identity,
            task_type=task_type,
            target_summary=target_summary,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )
        try:
            existing = self.store.get_payload(task["task_id"])
        except TaskNotFoundError:
            existing = None
        if existing is not None:
            if existing["payload"] != payload:
                raise ActionValidationError(
                    "idempotency key conflicts with a different action payload"
                )
            return {"task": task, "preview": existing["preview"]}
        if task["status"] == "draft":
            self.store.save_payload(task["task_id"], payload=payload, preview=preview)
            task = self.store.submit(task["task_id"], identity=identity)
        self.traces.record(
            "action_preview", trace_id, task_id=task["task_id"], action=task_type
        )
        return {"task": task, "preview": self.store.get_payload(task["task_id"])["preview"]}

    def _record_denied(
        self, task_id: str, identity: Identity, trace_id: str, error_type: str
    ) -> None:
        self.store.record_attempt(
            task_id,
            identity=identity,
            outcome="denied",
            error_type=error_type,
            trace_id=trace_id,
        )
        self.traces.record(
            "action_execution",
            trace_id,
            task_id=task_id,
            outcome="denied",
            error_type=error_type,
        )
