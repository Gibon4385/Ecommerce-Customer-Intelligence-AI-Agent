from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ecommerce_agent.data.contracts import coerce_value, validate_data

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("raw, expected", [("1", 1), ("1.0", 1), ("-2.000", -2)])
def test_integral_decimal_is_accepted(raw: str, expected: int) -> None:
    assert coerce_value(raw, "integer", {""}) == expected


@pytest.mark.parametrize("raw", ["1.5", "nan", "inf", "abc"])
def test_non_integral_or_non_finite_integer_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        coerce_value(raw, "integer", {""})


def test_string_list_and_na_normalization() -> None:
    assert coerce_value("P1, P2", "string_list", {""}) == ["P1", "P2"]
    assert coerce_value("N/A", "string", {"", "N/A"}) is None


def test_scalar_types_are_coerced() -> None:
    assert coerce_value("12.50", "decimal", {""}) == Decimal("12.50")
    assert coerce_value("0.25", "float", {""}) == 0.25
    assert coerce_value("2026-11-05", "date", {""}) == date(2026, 11, 5)
    assert coerce_value("2026-11-05T08:00:00", "timestamp", {""}) == datetime(
        2026, 11, 5, 8
    )
    assert coerce_value("true", "boolean", {""}) is True


def test_invalid_boolean_and_unknown_type_are_rejected() -> None:
    with pytest.raises(ValueError):
        coerce_value("yes", "boolean", {""})
    with pytest.raises(ValueError):
        coerce_value("value", "mystery", {""})


def test_duplicate_primary_key_is_reported(tmp_path: Path) -> None:
    data = tmp_path / "table.csv"
    with data.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows([["id"], ["A"], ["A"]])
    schema = tmp_path / "schema.yml"
    schema.write_text(
        "defaults: {null_values: ['']}\ntables:\n  t:\n    path: table.csv\n"
        "    primary_key: [id]\n    columns: {id: string}\n",
        encoding="utf-8",
    )
    result = validate_data(schema, tmp_path)
    assert any(issue.code == "duplicate_pk" for issue in result.issues)


def test_current_schema_is_valid() -> None:
    result = validate_data(ROOT / "data/schema.yml", ROOT / "data")
    assert result.issues == []
    assert result.tables_checked == 45

