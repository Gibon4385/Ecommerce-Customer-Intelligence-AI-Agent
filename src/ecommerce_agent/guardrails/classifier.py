from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .normalization import NormalizedInput


@dataclass(frozen=True)
class SafetyClassification:
    prompt_injection: bool = False
    jailbreak: bool = False
    role_impersonation: bool = False
    data_exfiltration: bool = False
    confidence: float = 1.0

    def blocked_category(self) -> str | None:
        for category in (
            "prompt_injection",
            "jailbreak",
            "role_impersonation",
            "data_exfiltration",
        ):
            if getattr(self, category):
                return category
        return None


class SafetyClassifier(Protocol):
    def classify(self, normalized: NormalizedInput) -> SafetyClassification: ...
