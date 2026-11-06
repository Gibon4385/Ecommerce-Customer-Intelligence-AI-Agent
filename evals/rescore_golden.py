from __future__ import annotations

import argparse
import json
from pathlib import Path

from ecommerce_agent.evaluation import evaluate_records, load_golden_set

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    source = json.loads((ROOT / args.input).read_text(encoding="utf-8"))
    _, cases = load_golden_set(ROOT / "evals/golden_set_v0.json")
    source["original_scoring"] = source["scoring"]
    source["scoring"] = evaluate_records(cases, source["records"])
    source["rescore_note"] = (
        "Deterministic rescore of unchanged second-run answers with calibrated synonym groups."
    )
    destination = ROOT / args.output
    destination.write_text(json.dumps(source, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(source["scoring"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
