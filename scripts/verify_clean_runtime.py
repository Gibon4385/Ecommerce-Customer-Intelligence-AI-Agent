from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ecommerce_agent.cli import build_runtime
from ecommerce_agent.data.contracts import validate_data
from scripts.bootstrap_demo_raw import bootstrap

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ecommerce-agent-clean-") as directory:
        target = Path(directory)
        for name in ("configs", "knowledge_base", "prompts"):
            shutil.copytree(ROOT / name, target / name)
        shutil.copytree(
            ROOT / "data",
            target / "data",
            ignore=shutil.ignore_patterns(
                "9_raw",
                "stg_users_hashed.csv",
                "mart_lookalike_hashed_email.csv",
            ),
        )
        assert not (target / "runtime").exists()
        assert not (target / "data/1_staging/stg_users_hashed.csv").exists()
        assert not (
            target / "data/3_marts/marketing/mart_lookalike_hashed_email.csv"
        ).exists()
        counts = bootstrap(target)
        assert counts["users"] > 0 and counts["orders"] > 0
        assert (target / "data/1_staging/stg_users_hashed.csv").is_file()
        assert (
            target / "data/3_marts/marketing/mart_lookalike_hashed_email.csv"
        ).is_file()
        contract = validate_data(target / "data/schema.yml", target / "data")
        assert contract.ok and contract.tables_checked == 45
        identities, gateway, traces = build_runtime(target)
        result = gateway.call(
            "get_daily_kpi",
            {"limit": 1},
            identity=identities.resolve("ops_01"),
            trace_id="clean-runtime-smoke",
        )
        assert len(result["data"]) == 1
        assert (target / "runtime/agent_tasks.duckdb").is_file()
        assert (target / "runtime/knowledge.duckdb").is_file()
        assert traces is not None
    print("clean runtime smoke: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
