from __future__ import annotations

import re
from dataclasses import dataclass


class InputGuardrailError(ValueError):
    def __init__(self, category: str, message: str):
        self.category = category
        self.trace_id: str | None = None
        super().__init__(message)


@dataclass(frozen=True)
class InputGuardrail:
    max_characters: int = 4000

    _patterns = {
        "prompt_injection": (
            r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
            r"忽略(?:前面|先前|以上|所有).{0,12}(?:指令|規則|要求)",
            r"(?<!不要)(?<!不可)(?<!不得)忽略.{0,12}(?:規則|指令|要求)",
            r"(?:reveal|print|show).{0,20}(?:system|developer)\s+prompt",
            r"(?:顯示|洩漏|輸出).{0,15}(?:系統提示|system prompt|developer message)",
        ),
        "jailbreak": (
            r"\b(?:jailbreak|dan mode|developer mode)\b",
            r"(?:解除|繞過|停用).{0,12}(?:安全|護欄|限制|rbac|權限)",
            r"bypass.{0,15}(?:guardrail|safety|rbac|authorization)",
        ),
        "role_impersonation": (
            r"(?:i am|i'm|act as|treat me as|make me)\s+(?:an?\s+)?admin\b",
            r"(?:我是|把我當成|將我設為|切換成|假裝我是).{0,8}(?:admin|管理員)",
        ),
        "malicious_sql": (
            r"\b(?:drop|truncate|alter)\s+(?:table|database|schema)\b",
            r"\bdelete\s+from\b",
            r"\b(?:insert|update)\s+(?:into\s+)?[a-z_][\w.]*\s+(?:set|values)\b",
            r"\bselect\b.{0,80}\bfrom\s+(?:raw|staging|intermediate)[\w.]*",
            r"(?:--|/\*)\s*(?:drop|delete|bypass|ignore)",
        ),
    }

    def validate(self, message: str) -> None:
        if not isinstance(message, str) or not message.strip():
            raise InputGuardrailError("empty_input", "message must not be empty")
        if len(message) > self.max_characters:
            raise InputGuardrailError(
                "oversized_input",
                f"message exceeds {self.max_characters} characters",
            )
        for category, patterns in self._patterns.items():
            if any(re.search(pattern, message, re.IGNORECASE | re.DOTALL) for pattern in patterns):
                raise InputGuardrailError(category, f"request blocked by {category} guardrail")
