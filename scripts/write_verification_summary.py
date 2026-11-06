from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/verification"


def main() -> int:
    coverage = json.loads((REPORTS / "coverage.json").read_text(encoding="utf-8"))
    data_quality = json.loads((REPORTS / "data_quality.json").read_text(encoding="utf-8"))
    xml_root = ElementTree.parse(REPORTS / "pytest-junit.xml").getroot()
    suite = xml_root if xml_root.tag == "testsuite" else xml_root.find("testsuite")
    assert suite is not None
    tests = int(suite.attrib["tests"])
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": data_quality["ok"] and failures == 0 and errors == 0 and skipped == 0,
        "deterministic_tests": {
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        },
        "coverage_percent": coverage["totals"]["percent_covered"],
        "data_contract": {
            "tables_checked": data_quality["tables_checked"],
            "rows_checked": data_quality["rows_checked"],
            "issues": len(data_quality["issues"]),
        },
        "optional_bigquery_parity": "not_run_no_production_decision",
    }
    path = REPORTS / "release_gate.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
