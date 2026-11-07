from __future__ import annotations

import hashlib
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.observability.tracing import JsonlTraceStore, redacted_content_record
from ecommerce_agent.tools.gateway import ToolGateway


@dataclass(frozen=True)
class DailyReportResult:
    markdown: str
    report_task_id: str
    trace_id: str
    delayed: bool


class DailyOperationsWorkflow:
    def __init__(self, gateway: ToolGateway, traces: JsonlTraceStore):
        self.gateway = gateway
        self.traces = traces

    def run(self, *, identity: Identity) -> DailyReportResult:
        trace_id = self.traces.new_trace_id()
        started = time.monotonic()
        self.traces.record(
            "interaction_started",
            trace_id,
            channel=identity.channel,
            request_type="workflow",
            workflow="daily_operations_report",
            role=identity.role,
            data_scope=identity.data_scope,
        )
        try:
            return self._execute(identity=identity, trace_id=trace_id, started=started)
        except Exception as exc:
            self.traces.record(
                "interaction_failed",
                trace_id,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                error_type=type(exc).__name__,
            )
            raise

    def _execute(
        self, *, identity: Identity, trace_id: str, started: float
    ) -> DailyReportResult:
        freshness = self._call("get_data_freshness", {}, identity, trace_id)
        daily = self._call("get_daily_kpi", {"limit": 29}, identity, trace_id)
        funnel = self._call(
            "get_conversion_funnel", {"category": "ALL", "limit": 1000}, identity, trace_id
        )
        category = self._call("get_category_sales", {"limit": 520}, identity, trace_id)
        brand = self._call("get_brand_health_alerts", {}, identity, trace_id)
        priorities = self._call("list_priority_actions", {"limit": 100}, identity, trace_id)
        tasks = self._call("list_tasks", {"limit": 20}, identity, trace_id)
        knowledge = self._call(
            "search_knowledge",
            {"query": "營收 漏斗 category sales 指標定義", "top_k": 3},
            identity,
            trace_id,
        )

        latest = daily["data"][0]
        visible_tasks = [
            row
            for row in tasks["data"]
            if not (
                row["task_type"] == "report"
                and row["idempotency_key"].startswith("daily-report-")
            )
        ]
        task_fingerprint = hashlib.sha256(
            repr(
                sorted(
                    (row["task_id"], row["status"], row["attempt_count"])
                    for row in visible_tasks
                )
            ).encode("utf-8")
        ).hexdigest()[:16]
        key_material = (
            f"{identity.user_id}|{daily['data_version']}|{daily['data_as_of']}|"
            f"{task_fingerprint}|daily"
        )
        idempotency_key = "daily-report-" + hashlib.sha256(
            key_material.encode("utf-8")
        ).hexdigest()[:24]
        delayed = self._is_delayed(freshness["data"], daily["data_as_of"])
        prior_week = daily["data"][7] if len(daily["data"]) > 7 else None
        average_28 = sum(
            (Decimal(row["revenue"]) for row in daily["data"][:28]), Decimal("0")
        ) / Decimal(min(len(daily["data"]), 28))
        latest_funnel = next(
            (row for row in funnel["data"] if row["date"] == latest["date"]), None
        )
        latest_week = max(row["week_start"] for row in category["data"])
        category_rows = [
            row for row in category["data"] if row["week_start"] == latest_week
        ]
        top_category = max(category_rows, key=lambda row: Decimal(row["revenue"]))
        high_risk = [row for row in brand["data"] if row["alert_level"] == "High Risk"]
        action_counts = Counter(row["recommended_action"] for row in priorities["data"])
        task_counts = Counter(row["status"] for row in visible_tasks)
        citations = [row["citation"] for row in knowledge["data"]]
        markdown = self._render(
            latest=latest,
            prior_week=prior_week,
            average_28=average_28,
            latest_funnel=latest_funnel,
            top_category=top_category,
            high_risk=high_risk,
            action_counts=action_counts,
            task_counts=task_counts,
            citations=citations,
            delayed=delayed,
            data_as_of=daily["data_as_of"],
        )
        report = self.gateway.call(
            "generate_report",
            {
                "report_type": "daily",
                "markdown": markdown,
                "idempotency_key": idempotency_key,
            },
            identity=identity,
            trace_id=trace_id,
        )["data"]
        self.traces.record(
            "workflow_complete",
            trace_id,
            workflow="daily_operations_report",
            report_task_id=report["task"]["task_id"],
            delayed=delayed,
            output=redacted_content_record(markdown),
        )
        self.traces.record(
            "interaction_completed",
            trace_id,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        return DailyReportResult(
            markdown=markdown,
            report_task_id=report["task"]["task_id"],
            trace_id=trace_id,
            delayed=delayed,
        )

    def _call(
        self,
        name: str,
        arguments: dict[str, Any],
        identity: Identity,
        trace_id: str,
    ) -> dict[str, Any]:
        return self.gateway.call(name, arguments, identity=identity, trace_id=trace_id)

    @staticmethod
    def _is_delayed(freshness: list[dict[str, Any]], data_as_of: str) -> bool:
        if any(row["status"] != "success" for row in freshness):
            return True
        return (datetime.now(UTC).date() - date.fromisoformat(data_as_of)).days > 1

    @staticmethod
    def _render(**context: Any) -> str:
        latest = context["latest"]
        prior = context["prior_week"]
        funnel = context["latest_funnel"]
        warning = (
            "> ⚠️ 資料延遲：以下結論僅反映現有快照，確定度降低。\n\n"
            if context["delayed"]
            else ""
        )
        prior_text = Decimal(prior["revenue"]) if prior else "N/A"
        funnel_text = (
            f"view→cart {funnel['view_to_cart_rate']}; cart→purchase "
            f"{funnel['cart_to_purchase_rate']}"
            if funnel
            else "資料不足"
        )
        risks = ", ".join(row["category"] for row in context["high_risk"]) or "無"
        actions = ", ".join(
            f"{name}: {count}" for name, count in sorted(context["action_counts"].items())
        )
        tasks = ", ".join(
            f"{name}: {count}" for name, count in sorted(context["task_counts"].items())
        ) or "無可見任務"
        citations = "\n".join(f"- `{item}`" for item in context["citations"])
        return (
            f"# 每日營運晨報（資料截至 {context['data_as_of']}）\n\n"
            f"{warning}"
            "## 資料事實\n\n"
            f"- 最新 completed-only 營收：{latest['revenue']}；訂單：{latest['orders']}；"
            f"AOV：{latest['aov']}。\n"
            f"- 上週同日營收：{prior_text}；近 28 日平均營收："
            f"{context['average_28'].quantize(Decimal('0.01'))}。\n"
            f"- 最新 ALL 漏斗：{funnel_text}。\n"
            f"- 最新週最高營收品類：{context['top_category']['category']} "
            f"({context['top_category']['revenue']})。\n"
            f"- High Risk 品類：{risks}。\n"
            f"- 優先行動摘要：{actions or '無'}。\n"
            f"- 任務狀態：{tasks}。\n\n"
            "## 推論與建議檢查\n\n"
            "- 漏斗或品類變化只代表需要進一步檢查，不直接推定因果。\n"
            "- 所有預估影響均為估計值，不是營收保證。\n\n"
            "## 引用\n\n"
            f"{citations}\n"
        )
