from __future__ import annotations

import csv
import hashlib
import importlib.util
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_ops_marts_completed_only_and_reconcile() -> None:
    build = _load_script("build_ops_marts")
    counts = build.build()
    assert all(value > 0 for value in counts.values())
    con = duckdb.connect(":memory:")
    output_revenue = con.execute(
        "SELECT SUM(revenue) FROM read_csv_auto(?)",
        [str(ROOT / "data/ops_marts/mart_ops_daily_kpi.csv")],
    ).fetchone()[0]
    source_revenue = con.execute(
        "SELECT SUM(total_amount) FROM read_csv_auto(?) WHERE order_status='completed'",
        [str(ROOT / "data/1_staging/stg_orders.csv")],
    ).fetchone()[0]
    assert abs(output_revenue - source_revenue) < 0.01


def test_funnel_contains_all_and_uses_purchase_events() -> None:
    path = ROOT / "data/ops_marts/mart_ops_conversion_funnel.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert any(row["category"] == "ALL" for row in rows)
    assert sum(int(row["purchase_users"]) for row in rows if row["category"] == "ALL") > 0


def test_gross_profit_is_unavailable_not_zero() -> None:
    for name in ("mart_ops_daily_kpi", "mart_ops_category_sales"):
        with (ROOT / "data/ops_marts" / f"{name}.csv").open(newline="", encoding="utf-8") as handle:
            assert all(row["gross_profit"] == "" for row in csv.DictReader(handle))


def test_synthetic_generation_is_reproducible_and_referential() -> None:
    synthetic = _load_script("generate_synthetic_ops")
    synthetic.generate()
    files = sorted((ROOT / "data/ops_marts").glob("mart_ops_*.csv"))
    excluded = ("daily", "funnel", "category_sales")
    selected = [path for path in files if not any(term in path.name for term in excluded)]
    first = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in selected}
    synthetic.generate()
    second = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in selected}
    assert first == second
    valid_users = {
        row["user_id"]
        for row in csv.DictReader(
            (ROOT / "data/2_intermediate/int_customer_segments.csv").open(encoding="utf-8")
        )
    }
    touches = csv.DictReader(
        (ROOT / "data/ops_marts/mart_ops_customer_touch_log.csv").open(encoding="utf-8")
    )
    assert all(row["user_id"] in valid_users for row in touches)
    pipeline = list(
        csv.DictReader(
            (ROOT / "data/ops_marts/mart_ops_pipeline_status.csv").open(encoding="utf-8")
        )
    )
    assert len(pipeline) == 15
    assert any(row["model_name"] == "mart_lookalike_hashed_email" for row in pipeline)

