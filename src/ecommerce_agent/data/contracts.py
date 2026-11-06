from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ContractIssue:
    table: str
    code: str
    detail: str


@dataclass
class ContractResult:
    tables_checked: int = 0
    rows_checked: int = 0
    issues: list[ContractIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def load_schema(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def coerce_value(value: str | None, declared_type: str, null_tokens: set[str]) -> Any:
    if value is None or value in null_tokens:
        return None
    if declared_type == "string":
        return value
    if declared_type == "string_list":
        return [part.strip() for part in value.split(",") if part.strip()]
    if declared_type == "integer":
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"not an integer: {value!r}") from exc
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError(f"not an integral finite value: {value!r}")
        return int(number)
    if declared_type == "decimal":
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"not a decimal: {value!r}") from exc
        if not number.is_finite():
            raise ValueError(f"not a finite decimal: {value!r}")
        return number
    if declared_type == "float":
        float_number = float(value)
        if not math.isfinite(float_number):
            raise ValueError(f"not a finite float: {value!r}")
        return float_number
    if declared_type == "date":
        return date.fromisoformat(value)
    if declared_type == "timestamp":
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if declared_type == "boolean":
        lowered = value.lower()
        if lowered not in {"true", "false"}:
            raise ValueError(f"not a boolean: {value!r}")
        return lowered == "true"
    raise ValueError(f"unknown declared type: {declared_type}")


def _null_tokens(schema: dict[str, Any], table: dict[str, Any], column: str) -> set[str]:
    tokens = set(schema.get("defaults", {}).get("null_values", [""]))
    tokens.update(table.get("null_values_by_column", {}).get(column, []))
    return tokens


def validate_data(schema_path: Path, data_root: Path) -> ContractResult:
    schema = load_schema(schema_path)
    result = ContractResult()
    for name, table in schema["tables"].items():
        result.tables_checked += 1
        path = data_root / table["path"]
        if not path.is_file():
            result.issues.append(ContractIssue(name, "missing_file", str(path)))
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            expected = list(table["columns"])
            if reader.fieldnames != expected:
                result.issues.append(
                    ContractIssue(
                        name, "columns", f"expected={expected}; actual={reader.fieldnames}"
                    )
                )
                continue
            seen_keys: set[tuple[Any, ...]] = set()
            primary_key = table.get("primary_key", [])
            nullable = set(table.get("nullable", []))
            for line_number, row in enumerate(reader, start=2):
                result.rows_checked += 1
                converted: dict[str, Any] = {}
                for column, declared_type in table["columns"].items():
                    try:
                        converted[column] = coerce_value(
                            row[column], declared_type, _null_tokens(schema, table, column)
                        )
                    except (ValueError, TypeError) as exc:
                        result.issues.append(
                            ContractIssue(name, "type", f"line {line_number} {column}: {exc}")
                        )
                    if converted.get(column) is None and column not in nullable:
                        result.issues.append(
                            ContractIssue(name, "null", f"line {line_number} {column}")
                        )
                key = tuple(converted.get(column) for column in primary_key)
                if any(value is None for value in key):
                    result.issues.append(ContractIssue(name, "null_pk", f"line {line_number}"))
                elif key in seen_keys:
                    result.issues.append(ContractIssue(name, "duplicate_pk", repr(key)))
                seen_keys.add(key)
                _check_constraints(result, name, table, converted, line_number)
    _check_duplicate_paths(result, schema, data_root)
    return result


def _check_constraints(
    result: ContractResult,
    name: str,
    table: dict[str, Any],
    row: dict[str, Any],
    line_number: int,
) -> None:
    constraints = table.get("constraints", {})
    if "period_0_to_12" in constraints:
        bounds = constraints["period_0_to_12"]
        for column in (key for key in row if key.startswith("period_")):
            value = row[column]
            if value is not None and not (bounds["min"] <= value <= bounds["max"]):
                result.issues.append(
                    ContractIssue(name, "range", f"line {line_number} {column}={value}")
                )
    for column, bounds in constraints.items():
        if column not in row or not isinstance(bounds, dict):
            continue
        value = row[column]
        in_range = value is None or bounds.get("min", value) <= value <= bounds.get("max", value)
        if not in_range:
            result.issues.append(
                ContractIssue(name, "range", f"line {line_number} {column}={value}")
            )


def _check_duplicate_paths(
    result: ContractResult, schema: dict[str, Any], data_root: Path
) -> None:
    for name, table in schema["tables"].items():
        canonical = data_root / table["path"]
        for relative in table.get("duplicate_paths_to_reject", []):
            duplicate = data_root / relative
            if duplicate.is_file():
                same = hashlib.sha256(canonical.read_bytes()).digest() == hashlib.sha256(
                    duplicate.read_bytes()
                ).digest()
                detail = f"{duplicate} duplicates canonical={canonical}; identical={same}"
                result.issues.append(ContractIssue(name, "duplicate_path", detail))

