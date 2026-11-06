from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


def _object(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


STRING = {"type": "string", "minLength": 1}
LIMIT = {"type": "integer", "minimum": 1}
DATE = {"type": "string", "format": "date"}


TOOL_SPECS = {
    spec.name: spec
    for spec in (
        ToolSpec(
            "get_customer_profile",
            "Get one customer C360 profile.",
            _object({"user_id": STRING}, ("user_id",)),
        ),
        ToolSpec(
            "list_priority_actions",
            "List actions sorted by priority score without dropping Monitor.",
            _object({"limit": LIMIT}),
        ),
        ToolSpec(
            "list_churn_risk_customers",
            "List churn-risk customers.",
            _object({"limit": LIMIT, "segment": STRING}),
        ),
        ToolSpec(
            "list_cart_abandoners",
            "List customers with abandoned products.",
            _object({"limit": LIMIT, "segment": STRING}),
        ),
        ToolSpec(
            "get_product_health",
            "Get product health by product or category.",
            _object({"product_id": STRING, "category": STRING}),
        ),
        ToolSpec(
            "get_brand_health_alerts",
            "Get aggregate brand-health alerts.",
            _object({"category": STRING}),
        ),
        ToolSpec(
            "get_sleepy_product_review",
            "Review products bought by dormant customers.",
            _object({"limit": LIMIT}),
        ),
        ToolSpec(
            "get_cross_sell_recommendations",
            "Get product affinity recommendations.",
            _object({"product_id": STRING}, ("product_id",)),
        ),
        ToolSpec(
            "get_cohort_analysis",
            "Get retention ratio or revenue/ARPU cohort data.",
            _object({"metric": {"enum": ["retention", "revenue", "arpu"]}}, ("metric",)),
        ),
        ToolSpec(
            "get_model_feature_importance", "Get global model feature importance.", _object({})
        ),
        ToolSpec(
            "get_daily_kpi",
            "Get completed-order daily KPIs.",
            _object({"start_date": DATE, "end_date": DATE, "limit": LIMIT}),
        ),
        ToolSpec(
            "get_conversion_funnel",
            "Get view/cart/purchase-event funnel; pass category='ALL' for an ALL request.",
            _object({"start_date": DATE, "end_date": DATE, "category": STRING, "limit": LIMIT}),
        ),
        ToolSpec(
            "get_category_sales",
            "Get completed-order category sales.",
            _object({"start_date": DATE, "end_date": DATE, "category": STRING, "limit": LIMIT}),
        ),
        ToolSpec(
            "get_campaign_performance",
            "Get synthetic campaign performance.",
            _object({"campaign_type": STRING, "segment": STRING}),
        ),
        ToolSpec(
            "check_audience_quality",
            "Deduplicate and exclude recently touched users.",
            _object(
                {"user_ids": {"type": "array", "items": STRING, "minItems": 1, "maxItems": 1000}},
                ("user_ids",),
            ),
        ),
        ToolSpec("get_data_freshness", "Get Mart pipeline freshness.", _object({})),
        ToolSpec(
            "list_tasks",
            "List role-scoped tasks persisted in the DuckDB task log.",
            _object({"limit": LIMIT}),
        ),
        ToolSpec(
            "get_task_status",
            "Get one role-scoped task from the DuckDB task log.",
            _object({"task_id": STRING}, ("task_id",)),
        ),
        ToolSpec(
            "search_knowledge",
            "Search authorized versioned knowledge and return source-line citations.",
            _object(
                {"query": STRING, "top_k": {"type": "integer", "minimum": 1, "maximum": 10}},
                ("query",),
            ),
        ),
        ToolSpec(
            "draft_retention_edm",
            "Create a non-executable retention EDM draft and task record.",
            _object(
                {"segment": STRING, "goal": STRING, "subject": STRING, "idempotency_key": STRING},
                ("segment", "goal", "subject", "idempotency_key"),
            ),
        ),
        ToolSpec(
            "send_edm",
            "Create a non-executable EDM dry-run pending independent approval.",
            _object(
                {
                    "draft_id": STRING,
                    "recipient_count": {"type": "integer", "minimum": 1, "maximum": 1000},
                    "discount_pct": {"type": "number", "minimum": 0, "maximum": 20},
                    "idempotency_key": STRING,
                },
                ("draft_id", "recipient_count", "discount_pct", "idempotency_key"),
            ),
        ),
        ToolSpec(
            "create_product_issue",
            "Create a non-executable product issue dry-run pending PM approval.",
            _object(
                {
                    "product_id": STRING,
                    "evidence": STRING,
                    "priority": {"enum": ["low", "medium", "high", "critical"]},
                    "idempotency_key": STRING,
                },
                ("product_id", "evidence", "priority", "idempotency_key"),
            ),
        ),
        ToolSpec(
            "generate_report",
            "Create a non-executable report preview pending approval.",
            _object(
                {
                    "report_type": {"enum": ["daily", "weekly", "campaign"]},
                    "markdown": STRING,
                    "idempotency_key": STRING,
                },
                ("report_type", "markdown", "idempotency_key"),
            ),
        ),
        ToolSpec(
            "approve_task",
            "Approve a pending action as an authorized user other than its requester.",
            _object({"task_id": STRING}, ("task_id",)),
        ),
        ToolSpec(
            "execute_task",
            "Execute an approved, unexpired action through the persistent mock adapter.",
            _object({"task_id": STRING}, ("task_id",)),
        ),
    )
}
