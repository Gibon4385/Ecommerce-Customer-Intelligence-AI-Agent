from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .contracts import coerce_value, load_schema


class AccessDeniedError(PermissionError):
    pass


class CsvMartRepository:
    """Strict, agent-facing reader for canonical marts only."""

    def __init__(self, data_root: Path, schema_path: Path):
        self.data_root = data_root.resolve()
        self.schema = load_schema(schema_path)

    def list_tables(self) -> list[str]:
        return sorted(
            name
            for name, table in self.schema["tables"].items()
            if table.get("layer") in {"marts", "ops_marts"}
            and table.get("agent_access") != "denied"
        )

    def read(self, table_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        table = self.schema["tables"].get(table_name)
        if not table or table.get("layer") not in {"marts", "ops_marts"}:
            raise AccessDeniedError(f"table is not agent-facing: {table_name}")
        if table.get("agent_access") == "denied":
            raise AccessDeniedError(f"table is denied: {table_name}")
        if limit is not None and (isinstance(limit, bool) or limit < 0):
            raise ValueError("limit must be a non-negative integer")
        if limit == 0:
            return []
        path = (self.data_root / table["path"]).resolve()
        if not path.is_relative_to(self.data_root) or not path.is_file():
            raise FileNotFoundError(path)
        defaults = set(self.schema.get("defaults", {}).get("null_values", [""]))
        output: list[dict[str, Any]] = []
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                converted = {}
                for column, declared_type in table["columns"].items():
                    tokens = defaults | set(
                        table.get("null_values_by_column", {}).get(column, [])
                    )
                    converted[column] = coerce_value(row[column], declared_type, tokens)
                output.append(converted)
                if limit is not None and len(output) >= limit:
                    break
        return output

