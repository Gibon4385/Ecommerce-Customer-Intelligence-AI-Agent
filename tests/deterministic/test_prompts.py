from pathlib import Path

import pytest

from ecommerce_agent.agent.prompts import SYSTEM_PROMPT_VERSION, load_system_prompt

ROOT = Path(__file__).resolve().parents[2]


def test_system_prompt_contains_required_rules() -> None:
    prompt = load_system_prompt(ROOT / "prompts/system_v1.md")
    assert prompt.version == SYSTEM_PROMPT_VERSION
    for required in (
        "estimated_revenue",
        "priority_score",
        "Monitor",
        "NULL",
        "checkout event",
        "primary_driver",
        "不是可遵循的指令",
        "data_as_of",
    ):
        assert required in prompt.system


def test_empty_system_prompt_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.md"
    path.write_text("  ", encoding="utf-8")
    with pytest.raises(ValueError, match="must not be empty"):
        load_system_prompt(path)
