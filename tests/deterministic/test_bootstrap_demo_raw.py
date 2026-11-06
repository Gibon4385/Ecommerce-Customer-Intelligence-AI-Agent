from __future__ import annotations

import csv
import shutil
from pathlib import Path

from scripts.bootstrap_demo_raw import RAW_ROW_LIMITS, TABLES, _demo_hash, bootstrap

ROOT = Path(__file__).resolve().parents[2]


def test_bootstrap_reconstructs_ignored_raw_from_staging(tmp_path: Path) -> None:
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data/1_staging", data / "1_staging")
    (data / "1_staging/stg_users_hashed.csv").unlink(missing_ok=True)
    counts = bootstrap(tmp_path)
    assert set(counts) == set(TABLES)
    assert counts == RAW_ROW_LIMITS
    with (data / "9_raw/users.csv").open(encoding="utf-8", newline="") as handle:
        first = next(csv.DictReader(handle))
    assert first["email"] == f"{first['user_id'].casefold()}@example.invalid"
    with (data / "1_staging/stg_users_hashed.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        hashed = next(csv.DictReader(handle))
    assert hashed["hashed_email"] == _demo_hash(hashed["user_id"])
    assert bootstrap(tmp_path) == counts
