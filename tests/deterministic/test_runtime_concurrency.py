from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime-root"
    root.mkdir()
    shutil.copytree(ROOT / "configs", root / "configs")
    shutil.copytree(ROOT / "knowledge_base", root / "knowledge_base")
    (root / "data").mkdir()
    shutil.copy2(ROOT / "data/schema.yml", root / "data/schema.yml")
    return root


def _build_runtime_in_subprocess(root: Path) -> subprocess.CompletedProcess[str]:
    program = (
        "import sys; "
        "from pathlib import Path; "
        "from ecommerce_agent.cli import RuntimeBusyError, build_runtime; "
        "root = Path(sys.argv[1]); "
        "\ntry:\n build_runtime(root)\n"
        "except RuntimeBusyError as exc:\n "
        "print(type(exc).__name__ + ': ' + str(exc)); sys.exit(3)\n"
        "print('runtime-ready')"
    )
    return subprocess.run(
        [sys.executable, "-c", program, str(root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def test_second_build_runtime_exposes_duckdb_cross_process_write_limit(
    tmp_path: Path,
) -> None:
    root = _runtime_root(tmp_path)
    task_path = root / "runtime/agent_tasks.duckdb"
    task_path.parent.mkdir(parents=True)

    holder = duckdb.connect(str(task_path))
    try:
        blocked = _build_runtime_in_subprocess(root)
    finally:
        holder.close()

    assert blocked.returncode == 3
    assert blocked.stdout.startswith("RuntimeBusyError: Local runtime is already in use")
    assert blocked.stderr == ""
    assert "_duckdb.IOException" not in blocked.stdout
    assert "runtime-ready" not in blocked.stdout

    recovered = _build_runtime_in_subprocess(root)
    assert recovered.returncode == 0, recovered.stderr
    assert recovered.stdout.strip() == "runtime-ready"
