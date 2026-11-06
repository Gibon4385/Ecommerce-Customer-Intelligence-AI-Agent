from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SYSTEM_PROMPT_VERSION = "system_v1"


@dataclass(frozen=True)
class PromptBundle:
    version: str
    system: str


def load_system_prompt(path: Path) -> PromptBundle:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError("system prompt must not be empty")
    return PromptBundle(version=SYSTEM_PROMPT_VERSION, system=content)

