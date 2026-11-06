from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_rules_and_document_map_exist() -> None:
    assert (ROOT / "AGENTS.md").is_file()
    assert (ROOT / "docs/kickoff_prompt.md").is_file()
    assert (ROOT / "docs/verification/thresholds.md").is_file()
    assert (ROOT / "docs/verification/traceability_matrix.md").is_file()
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8").strip() == "See `AGENTS.md`."


def test_readme_records_confirmed_definitions() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "completed" in readme
    assert "沒有 `checkout` event" in readme
    assert "gross_profit" in readme and "`NULL`" in readme

