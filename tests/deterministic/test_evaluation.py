from __future__ import annotations

import json
from pathlib import Path

import pytest

from ecommerce_agent.evaluation import GoldenCase, evaluate_case, evaluate_records, load_golden_set

ROOT = Path(__file__).resolve().parents[2]


def _case() -> GoldenCase:
    return GoldenCase(
        id="T1",
        user_id="ops_01",
        question="latest KPI",
        expected_calls=[{"name": "get_daily_kpi", "arguments": {"limit": 10}}],
        must_include=["completed", "資料截至"],
        must_not_include=["即時"],
        critical=True,
    )


def test_evaluator_accepts_subset_arguments_and_required_facts() -> None:
    result = evaluate_case(
        _case(),
        {
            "id": "T1",
            "calls": [
                {"name": "get_daily_kpi", "arguments": {"limit": 10, "end_date": "2026-07-06"}}
            ],
            "answer": "completed 訂單，資料截至 2026-07-06。",
            "error": None,
        },
    )
    assert result["passed"] is True


def test_evaluator_detects_wrong_tool_missing_fact_and_forbidden_content() -> None:
    result = evaluate_case(
        _case(),
        {
            "id": "T1",
            "calls": [{"name": "get_data_freshness", "arguments": {}}],
            "answer": "這是即時資料。",
            "error": None,
        },
    )
    assert result["passed"] is False
    assert not result["tool_selection_pass"]
    assert result["missing_facts"] == ["completed", "資料截至"]
    assert result["forbidden_found"] == ["即時"]


def test_evaluator_allows_explicit_negation_of_forbidden_claim() -> None:
    record = {
        "id": "T1",
        "calls": [{"name": "get_daily_kpi", "arguments": {"limit": 10}}],
        "answer": "completed，資料截至昨日；這不是即時資料。",
        "error": None,
    }
    case = _case()
    case = GoldenCase(**{**case.__dict__, "must_not_include": ["即時"]})
    assert evaluate_case(case, record)["forbidden_pass"] is True


def test_evaluator_accepts_declared_fact_synonyms() -> None:
    case = _case()
    case = GoldenCase(**{**case.__dict__, "must_include_any": [["成本資料不可得", "缺少成本"]]})
    record = {
        "id": "T1",
        "calls": [{"name": "get_daily_kpi", "arguments": {"limit": 10}}],
        "answer": "completed，資料截至昨日，成本資料不可得。",
        "error": None,
    }
    assert evaluate_case(case, record)["facts_pass"] is True


def test_golden_set_has_30_unique_well_formed_cases() -> None:
    metadata, cases = load_golden_set(ROOT / "evals/golden_set_v0.json")
    assert metadata == {"version": "golden_v0", "prompt_version": "system_v1"}
    assert len(cases) == 30
    assert len({case.id for case in cases}) == 30
    assert sum(case.critical for case in cases) >= 10


@pytest.mark.parametrize("case_id", ["G024", "G025"])
def test_deterministic_guardrail_refusal_satisfies_security_cases(case_id: str) -> None:
    _, cases = load_golden_set(ROOT / "evals/golden_set_v0.json")
    case = next(item for item in cases if item.id == case_id)
    result = evaluate_case(
        case,
        {
            "id": case.id,
            "calls": [],
            "answer": "無法列出或提供未授權資料：請求已被確定性安全政策阻擋。",
            "error": None,
        },
    )
    assert result["passed"] is True


def test_aggregate_scores_and_missing_record() -> None:
    case = _case()
    report = evaluate_records([case], [])
    assert report["case_count"] == 1
    assert report["pass_rate"] == 0
    assert report["critical_pass_rate"] == 0


def test_duplicate_golden_ids_are_rejected(tmp_path: Path) -> None:
    item = {
        "id": "same",
        "user_id": "ops_01",
        "question": "q",
        "expected_calls": [],
        "must_include": [],
        "must_not_include": [],
        "critical": False,
    }
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps({"cases": [item, item]}), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load_golden_set(path)

