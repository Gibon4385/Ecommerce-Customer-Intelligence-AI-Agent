from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = DATA / "ops_marts"
MODELS = ROOT / "warehouse" / "models"


def _sql_string(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def build() -> dict[str, int]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(":memory:")
    for name in ("orders", "order_items", "events", "products", "users"):
        path = DATA / "1_staging" / f"stg_{name}.csv"
        connection.execute(
            f"CREATE VIEW stg_{name} AS "
            f"SELECT * FROM read_csv_auto({_sql_string(path)}, header=true)"
        )
    counts: dict[str, int] = {}
    for model in (
        "mart_ops_daily_kpi",
        "mart_ops_conversion_funnel",
        "mart_ops_category_sales",
    ):
        sql = (MODELS / f"{model}.sql").read_text(encoding="utf-8").strip().rstrip(";")
        output = OUTPUT / f"{model}.csv"
        connection.execute(
            f"COPY ({sql}) TO {_sql_string(output)} (HEADER, DELIMITER ',')"
        )
        row = connection.execute(f"SELECT COUNT(*) FROM ({sql})").fetchone()
        assert row is not None
        counts[model] = row[0]
    connection.close()
    return counts


if __name__ == "__main__":
    for table, count in build().items():
        print(f"{table}: {count} rows")

