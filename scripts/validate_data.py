from __future__ import annotations

import json
from pathlib import Path

from ecommerce_agent.data.contracts import validate_data

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = validate_data(ROOT / "data" / "schema.yml", ROOT / "data")
    payload = {
        "ok": result.ok,
        "tables_checked": result.tables_checked,
        "rows_checked": result.rows_checked,
        "issues": [issue.__dict__ for issue in result.issues],
    }
    report = ROOT / "reports" / "verification" / "data_quality.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

