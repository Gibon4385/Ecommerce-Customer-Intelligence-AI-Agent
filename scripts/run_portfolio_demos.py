from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ecommerce_agent.cli import build_runtime
from ecommerce_agent.workflows import DailyOperationsWorkflow

ROOT = Path(__file__).resolve().parents[1]


def _call(gateway: Any, traces: Any, identity: Any, name: str, arguments: dict[str, Any]):
    return gateway.call(
        name,
        arguments,
        identity=identity,
        trace_id=traces.new_trace_id(),
    )["data"]


def _approve_and_execute(
    gateway: Any, traces: Any, requester: Any, approver: Any, task: dict[str, Any]
) -> dict[str, Any]:
    task_id = task["task_id"]
    if task["status"] == "pending_approval":
        task = _call(gateway, traces, approver, "approve_task", {"task_id": task_id})
    if task["status"] == "approved":
        task = _call(gateway, traces, requester, "execute_task", {"task_id": task_id})
    return task


def main() -> int:
    identities, gateway, traces = build_runtime(ROOT)

    ops = identities.resolve("ops_01")
    report = DailyOperationsWorkflow(gateway, traces).run(identity=ops)

    marketing = identities.resolve("marketing_01")
    marketing_approver = identities.resolve("marketing_approver")
    sleepy = _call(gateway, traces, marketing, "get_sleepy_product_review", {"limit": 3})
    churn = _call(gateway, traces, marketing, "list_churn_risk_customers", {"limit": 5})
    audience_ids = [row["user_id"] for row in churn]
    audience = _call(
        gateway, traces, marketing, "check_audience_quality", {"user_ids": audience_ids}
    )
    _call(
        gateway,
        traces,
        marketing,
        "search_knowledge",
        {"query": "行銷聯絡頻率 核准", "top_k": 3},
    )
    draft = _call(
        gateway,
        traces,
        marketing,
        "draft_retention_edm",
        {
            "segment": "Dormant High-Value Customer",
            "goal": "Portfolio retention demo",
            "subject": "A reason to return",
            "idempotency_key": "demo-retention-draft-v1",
        },
    )
    send = _call(
        gateway,
        traces,
        marketing,
        "send_edm",
        {
            "draft_id": draft["task"]["task_id"],
            "recipient_count": max(1, len(audience["eligible_user_ids"])),
            "discount_pct": 10,
            "idempotency_key": "demo-retention-send-v1",
        },
    )
    send_task = _approve_and_execute(
        gateway, traces, marketing, marketing_approver, send["task"]
    )

    pm = identities.resolve("pm_01")
    pm_approver = identities.resolve("pm_approver")
    alerts = _call(gateway, traces, pm, "get_brand_health_alerts", {})
    product = _call(
        gateway, traces, pm, "get_product_health", {"product_id": "P000001"}
    )
    issue = _call(
        gateway,
        traces,
        pm,
        "create_product_issue",
        {
            "product_id": "P000001",
            "evidence": "Deterministic demo based on product-health and brand-alert tools",
            "priority": "high",
            "idempotency_key": "demo-product-issue-p000001-v1",
        },
    )
    issue_task = _approve_and_execute(gateway, traces, pm, pm_approver, issue["task"])

    summary = {
        "workflow_1_daily_report": {
            "report_task_id": report.report_task_id,
            "delayed": report.delayed,
        },
        "workflow_2_retention_campaign": {
            "sleepy_products": len(sleepy),
            "eligible_audience": len(audience["eligible_user_ids"]),
            "task_status": send_task["status"],
            "external_ref": send_task["external_ref"],
        },
        "workflow_3_product_issue": {
            "brand_alerts": len(alerts),
            "product_rows": len(product),
            "task_status": issue_task["status"],
            "external_ref": issue_task["external_ref"],
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
