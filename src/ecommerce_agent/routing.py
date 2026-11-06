from __future__ import annotations

from dataclasses import dataclass

QUERY_TOOLS = {
    "get_customer_profile",
    "get_product_health",
    "get_data_freshness",
    "get_task_status",
    "list_tasks",
    "search_knowledge",
}
ANALYTIC_TOOLS = {
    "get_brand_health_alerts",
    "get_sleepy_product_review",
    "get_cohort_analysis",
    "get_model_feature_importance",
    "get_daily_kpi",
    "get_conversion_funnel",
    "get_category_sales",
    "get_campaign_performance",
    "list_priority_actions",
    "list_churn_risk_customers",
    "list_cart_abandoners",
    "get_cross_sell_recommendations",
    "check_audience_quality",
    "search_knowledge",
}
ACTION_TOOLS = {
    "draft_retention_edm",
    "send_edm",
    "create_product_issue",
    "generate_report",
    "approve_task",
    "execute_task",
}


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    model_tier: str
    tool_names: frozenset[str]
    confidence: float
    cacheable: bool


class DeterministicRouter:
    def route(self, message: str) -> RouteDecision:
        folded = message.casefold()
        if any(
            token in folded
            for token in (
                "寄送",
                "發送",
                "建立 issue",
                "create issue",
                "核准",
                "執行任務",
                "send edm",
            )
        ):
            return RouteDecision("action", "large", frozenset(ACTION_TOOLS), 0.95, False)
        if any(token in folded for token in ("晨報", "日報", "週報", "daily report")):
            return RouteDecision(
                "report", "large", frozenset(ANALYTIC_TOOLS | {"generate_report"}), 0.95, False
            )
        if any(token in folded for token in ("策略", "企劃", "建議方案", "campaign plan")):
            return RouteDecision(
                "strategy", "large", frozenset(ANALYTIC_TOOLS), 0.9, True
            )
        if any(token in folded for token in ("為什麼", "原因", "異常", "診斷", "比較", "趨勢")):
            return RouteDecision(
                "diagnosis", "large", frozenset(ANALYTIC_TOOLS | QUERY_TOOLS), 0.9, True
            )
        if len(message.strip()) < 4:
            return RouteDecision(
                "unknown", "large", frozenset(QUERY_TOOLS | ANALYTIC_TOOLS), 0.3, True
            )
        return RouteDecision("query", "small", frozenset(QUERY_TOOLS | ANALYTIC_TOOLS), 0.8, True)
