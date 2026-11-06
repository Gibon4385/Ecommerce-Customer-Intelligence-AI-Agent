from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from ecommerce_agent.data.repository import AccessDeniedError, CsvMartRepository

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repository() -> CsvMartRepository:
    return CsvMartRepository(ROOT / "data", ROOT / "data/schema.yml")


def test_raw_and_intermediate_are_denied(repository: CsvMartRepository) -> None:
    for table in ("raw_users", "stg_users", "int_customer_segments"):
        with pytest.raises(AccessDeniedError):
            repository.read(table)


def test_canonical_hashed_email_is_used(repository: CsvMartRepository) -> None:
    rows = repository.read("mart_lookalike_hashed_email", limit=1)
    assert len(rows) == 1
    assert len(rows[0]["hashed_email"]) == 64


def test_null_and_integral_decimal_are_normalized(repository: CsvMartRepository) -> None:
    rows = repository.read("mart_product_health_report")
    assert any(row["top_pain_points"] is None for row in rows)
    c360 = repository.read("mart_c360_table")
    assert all(row["total_views"] is None or isinstance(row["total_views"], int) for row in c360)
    assert isinstance(c360[0]["monetary"], Decimal)


def test_cart_product_ids_are_lists(repository: CsvMartRepository) -> None:
    row = repository.read("mart_cart_abandonment_list", limit=1)[0]
    assert isinstance(row["abandoned_product_ids"], list)
    assert all(product.startswith("P") for product in row["abandoned_product_ids"])


def test_invalid_limit_is_rejected(repository: CsvMartRepository) -> None:
    with pytest.raises(ValueError):
        repository.read("mart_c360_table", limit=-1)
    assert repository.read("mart_c360_table", limit=0) == []


def test_table_inventory_only_contains_agent_facing_marts(
    repository: CsvMartRepository,
) -> None:
    tables = repository.list_tables()
    assert "mart_c360_table" in tables
    assert "raw_users" not in tables
    with pytest.raises(AccessDeniedError):
        repository.read("does_not_exist")


def test_explicit_denial_and_missing_file_are_enforced(repository: CsvMartRepository) -> None:
    repository.schema["tables"]["blocked_mart"] = {
        "layer": "marts",
        "agent_access": "denied",
        "path": "3_marts/missing.csv",
        "columns": {},
    }
    with pytest.raises(AccessDeniedError):
        repository.read("blocked_mart")
    repository.schema["tables"]["blocked_mart"]["agent_access"] = "role_restricted"
    with pytest.raises(FileNotFoundError):
        repository.read("blocked_mart")

