from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GoldenCase:
    id: str
    user_id: str
    question: str
    expected_calls: list[dict[str, Any]]
    must_include: list[str]
    must_not_include: list[str]
    critical: bool
    must_include_any: list[list[str]] = field(default_factory=list)


def load_golden_set(path: Path) -> tuple[dict[str, Any], list[GoldenCase]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = [GoldenCase(**item) for item in payload["cases"]]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("golden case IDs must be unique")
    return {key: value for key, value in payload.items() if key != "cases"}, cases


def _is_subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _is_subset(value, actual[key]) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return expected == actual
    return expected == actual


def _contains_unnegated(text: str, phrase: str) -> bool:
    start = 0
    negators = ("不", "不是", "不得", "不能", "不可", "並非", "非", "無法", "未", "禁止")
    while (index := text.find(phrase, start)) >= 0:
        prefix = text[max(0, index - 8) : index]
        if not any(negator in prefix for negator in negators):
            return True
        start = index + len(phrase)
    return False


def evaluate_case(case: GoldenCase, record: dict[str, Any]) -> dict[str, Any]:
    actual_calls = record.get("calls", [])
    expected_names = [call["name"] for call in case.expected_calls]
    actual_names = [call.get("name") for call in actual_calls]
    tool_selection_pass = expected_names == actual_names
    parameter_pass = tool_selection_pass and all(
        _is_subset(expected.get("arguments", {}), actual.get("arguments", {}))
        for expected, actual in zip(case.expected_calls, actual_calls, strict=True)
    )
    answer = str(record.get("answer") or "")
    folded = answer.casefold()
    included = [text for text in case.must_include if text.casefold() in folded]
    any_groups_pass = [
        any(option.casefold() in folded for option in group) for group in case.must_include_any
    ]
    forbidden_found = [
        text for text in case.must_not_include if _contains_unnegated(folded, text.casefold())
    ]
    facts_pass = len(included) == len(case.must_include) and all(any_groups_pass)
    forbidden_pass = not forbidden_found
    passed = (
        record.get("error") is None
        and tool_selection_pass
        and parameter_pass
        and facts_pass
        and forbidden_pass
    )
    return {
        "id": case.id,
        "critical": case.critical,
        "passed": passed,
        "tool_selection_pass": tool_selection_pass,
        "parameter_pass": parameter_pass,
        "facts_pass": facts_pass,
        "forbidden_pass": forbidden_pass,
        "missing_facts": [text for text in case.must_include if text not in included],
        "missing_fact_groups": [
            group
            for group, passed_group in zip(
                case.must_include_any, any_groups_pass, strict=True
            )
            if not passed_group
        ],
        "forbidden_found": forbidden_found,
        "expected_tools": expected_names,
        "actual_tools": actual_names,
        "error": record.get("error"),
    }


def evaluate_records(cases: list[GoldenCase], records: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {record["id"]: record for record in records}
    results = [
        evaluate_case(case, by_id.get(case.id, {"id": case.id, "error": "missing record"}))
        for case in cases
    ]
    count = len(results)

    def rate(field: str) -> float:
        return round(sum(bool(item[field]) for item in results) / count, 4) if count else 0.0

    critical = [item for item in results if item["critical"]]
    return {
        "case_count": count,
        "pass_rate": rate("passed"),
        "tool_selection_accuracy": rate("tool_selection_pass"),
        "parameter_accuracy": rate("parameter_pass"),
        "required_facts_accuracy": rate("facts_pass"),
        "forbidden_content_compliance": rate("forbidden_pass"),
        "critical_pass_rate": (
            round(sum(item["passed"] for item in critical) / len(critical), 4) if critical else 1.0
        ),
        "results": results,
    }

