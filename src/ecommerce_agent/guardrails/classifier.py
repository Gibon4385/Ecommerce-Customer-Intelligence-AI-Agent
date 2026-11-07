from __future__ import annotations

import re
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


@dataclass(frozen=True)
class DeterministicSafetyClassifier:
    """High-confidence multilingual rules used by the local runtime.

    This deliberately covers only known, explainable high-risk constructions. It is
    not a general semantic classifier; unsupported languages fail closed through a
    low-confidence result.
    """

    _patterns = {
        "prompt_injection": (
            r"(?:以前|前|上記).{0,16}(?:指示|命令).{0,16}(?:無視|従わない)",
            r"(?:無視|忘れて).{0,16}(?:以前|前|上記).{0,16}(?:指示|命令)",
            r"(?:이전|위의|앞선).{0,16}(?:지시|명령).{0,16}(?:무시|잊어)",
            r"(?:ignora|omite).{0,20}(?:instrucciones|reglas).{0,20}(?:anteriores|previas)",
        ),
        "jailbreak": (
            r"(?:desactiva|deshabilita|evita).{0,20}(?:seguridad|rbac|restricciones)",
            r"(?:セキュリティ|制限|rbac).{0,16}(?:解除|無効|回避)",
            r"(?:보안|제한|rbac).{0,16}(?:해제|비활성화|우회)",
        ),
        "role_impersonation": (
            r"(?:私は|わたしは).{0,12}(?:管理者|admin)",
            r"(?:저는|나는|나를).{0,12}(?:관리자|어드민|admin)",
            r"(?:soy|trátame como|actúa como).{0,12}(?:administrador|admin)",
        ),
        "data_exfiltration": (
            r"(?:decode|decrypt|export|dump|exfiltrate).{0,40}"
            r"(?:restricted|customer|user).{0,20}(?:identifier|email|data)",
            r"(?:書き出|出力|抽出).{0,24}(?:顧客|利用者).{0,16}(?:識別子|メール|データ)",
            r"(?:내보내|추출|유출).{0,24}(?:고객|사용자).{0,16}(?:식별자|이메일|데이터)",
            r"(?:exporta|extrae|filtra).{0,24}(?:identificadores|correos|datos).{0,16}"
            r"(?:restringidos|clientes|usuarios)",
        ),
    }

    def classify(self, normalized: NormalizedInput) -> SafetyClassification:
        if not normalized.language.supported:
            return SafetyClassification(confidence=0.0)

        def matches(category: str) -> bool:
            return any(
                re.search(pattern, normalized.canonical, re.IGNORECASE | re.DOTALL)
                for pattern in self._patterns[category]
            )

        return SafetyClassification(
            prompt_injection=matches("prompt_injection"),
            jailbreak=matches("jailbreak"),
            role_impersonation=matches("role_impersonation"),
            data_exfiltration=matches("data_exfiltration"),
            confidence=0.99,
        )
