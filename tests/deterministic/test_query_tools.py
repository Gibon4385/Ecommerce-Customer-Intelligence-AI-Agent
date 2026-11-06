from __future__ import annotations

from pathlib import Path

import pytest

from ecommerce_agent.data.repository import CsvMartRepository
from ecommerce_agent.rag.store import DuckDBRagStore
from ecommerce_agent.tasks.store import DuckDBTaskStore
from ecommerce_agent.tools.query import QueryTools, ToolInputError, json_safe

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tools(tmp_path_factory: pytest.TempPathFactory) -> QueryTools:
    task_store = DuckDBTaskStore(tmp_path_factory.mktemp("tasks") / "tasks.duckdb")
    rag_store = DuckDBRagStore(tmp_path_factory.mktemp("rag") / "knowledge.duckdb")
    rag_store.rebuild_from_manifest(ROOT / "configs/rag_sources.yaml", root=ROOT)
    return QueryTools(
        CsvMartRepository(ROOT / "data", ROOT / "data/schema.yml"), task_store, rag_store
    )


def test_customer_profile_success_and_empty(tools: QueryTools) -> None:
    assert tools.get_customer_profile("U000001").data is not None
    assert tools.get_customer_profile("missing").data is None
    with pytest.raises(ToolInputError):
        tools.get_customer_profile("")


def test_priority_actions_are_sorted_and_keep_monitor(tools: QueryTools) -> None:
    result = tools.list_priority_actions(100)
    scores = [row["priority_score"] for row in result.data]
    assert scores == sorted(scores, reverse=True)
    assert any(row["recommended_action"] == "Monitor" for row in result.data)
    assert result.data_version != "unknown" and result.data_as_of == "2026-07-06"
    with pytest.raises(ToolInputError):
        tools.list_priority_actions(101)


def test_customer_lists_filters_and_list_parsing(tools: QueryTools) -> None:
    churn = tools.list_churn_risk_customers(limit=5)
    assert len(churn.data) == 5
    segment = churn.data[0]["segment"]
    assert all(
        row["segment"] == segment
        for row in tools.list_churn_risk_customers(segment=segment).data
    )
    cart = tools.list_cart_abandoners(limit=5)
    assert all(isinstance(row["abandoned_product_ids"], list) for row in cart.data)
    assert tools.list_cart_abandoners(segment=cart.data[0]["segment"]).data


def test_product_brand_and_sleepy_tools(tools: QueryTools) -> None:
    product = tools.get_product_health(product_id="P000001")
    assert all(row["product_id"] == "P000001" for row in product.data)
    category = tools.get_product_health(category="Electronics")
    assert all(row["category"] == "Electronics" for row in category.data)
    with pytest.raises(ToolInputError):
        tools.get_product_health()
    with pytest.raises(ToolInputError):
        tools.get_product_health(product_id="P1", category="x")
    alerts = tools.get_brand_health_alerts()
    assert alerts.data
    one = tools.get_brand_health_alerts(alerts.data[0]["category"])
    assert len(one.data) == 1
    assert len(tools.get_sleepy_product_review(limit=3).data) == 3


def test_affinity_cohort_and_model_tools(tools: QueryTools) -> None:
    affinity_rows = tools.repository.read("mart_product_affinity")
    product_id = affinity_rows[0]["product_a_id"]
    assert tools.get_cross_sell_recommendations(product_id).data
    assert tools.get_cross_sell_recommendations("missing").data == []
    with pytest.raises(ToolInputError):
        tools.get_cross_sell_recommendations("")
    retention = tools.get_cohort_analysis("retention")
    assert retention.data and "ratios" in retention.notices[0]
    assert tools.get_cohort_analysis("arpu").data
    with pytest.raises(ToolInputError):
        tools.get_cohort_analysis("profit")
    importance = tools.get_model_feature_importance().data
    assert importance[0]["importance_gain"] >= importance[-1]["importance_gain"]


def test_operational_tools_dates_filters_and_notices(tools: QueryTools) -> None:
    daily = tools.get_daily_kpi(limit=10)
    assert len(daily.data) == 10
    assert daily.data[0]["date"] >= daily.data[-1]["date"]
    selected_date = daily.data[0]["date"].isoformat()
    assert len(tools.get_daily_kpi(start_date=selected_date, end_date=selected_date).data) == 1
    funnel = tools.get_conversion_funnel(category="ALL", limit=10)
    assert all(row["category"] == "ALL" for row in funnel.data)
    sales = tools.get_category_sales(limit=5)
    assert len(sales.data) == 5
    campaign = tools.get_campaign_performance(campaign_type="EDM")
    assert all(row["campaign_type"] == "EDM" for row in campaign.data)
    assert tools.get_campaign_performance(segment=campaign.data[0]["target_segment"]).data
    with pytest.raises(ToolInputError):
        tools.get_daily_kpi(start_date="bad")
    with pytest.raises(ToolInputError):
        tools.get_daily_kpi(start_date="2026-01-02", end_date="2026-01-01")


def test_audience_freshness_and_empty_task_store(tools: QueryTools) -> None:
    touches = tools.repository.read("mart_ops_customer_touch_log", limit=2)
    ids = [touches[0]["user_id"], touches[0]["user_id"], "U999999"]
    result = tools.check_audience_quality(ids).data
    assert result["input_count"] == 3 and result["unique_count"] == 2
    with pytest.raises(ToolInputError):
        tools.check_audience_quality([])
    assert len(tools.get_data_freshness().data) == 15
    from ecommerce_agent.auth.identity import Identity

    identity = Identity("ops_01", "Ops", "aggregate", "test")
    assert tools.list_tasks(identity=identity).data == []
    assert tools.get_task_status("T1", identity=identity).data is None
    with pytest.raises(ToolInputError):
        tools.get_task_status("")
    assert isinstance(json_safe(tools.get_daily_kpi(limit=1).data), list)


def test_knowledge_tool_evidence_empty_and_missing_store(tools: QueryTools) -> None:
    from ecommerce_agent.auth.identity import Identity

    identity = Identity("support_01", "Support", "single_customer", "test")
    result = tools.search_knowledge("客戶聯絡頻率", identity=identity)
    assert result.data and result.data[0]["citation"]
    assert "instructions" in result.notices[0]
    empty = tools.search_knowledge("量子火箭庫存政策", identity=identity)
    assert empty.data == [] and "do not invent" in empty.notices[0]
    with pytest.raises(ToolInputError, match="RAG store"):
        QueryTools(tools.repository).search_knowledge("policy", identity=identity)
    with pytest.raises(ToolInputError, match="action service"):
        tools.generate_report(
            report_type="daily",
            markdown="# Report",
            idempotency_key="missing-action-service",
            identity=identity,
            trace_id="trace",
        )

