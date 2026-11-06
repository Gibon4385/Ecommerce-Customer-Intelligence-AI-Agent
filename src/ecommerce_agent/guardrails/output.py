from __future__ import annotations

import re
from dataclasses import dataclass

from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.observability.tracing import redact_text


class OutputGuardrailError(ValueError):
    def __init__(self, category: str, message: str):
        self.category = category
        self.trace_id: str | None = None
        super().__init__(message)


@dataclass(frozen=True)
class OutputGuardrail:
    _forbidden_commitments = (
        r"(?:保證|承諾).{0,12}(?:營收|收益|獲利|轉換|成效)",
        r"(?:revenue|profit|conversion).{0,12}(?:guarantee|guaranteed)",
        r"(?:guarantee|guaranteed).{0,12}(?:revenue|profit|conversion)",
    )
    _unauthorized_offers = (
        r"(?:提供|給予|發放|(?<!未)核准).{0,15}(?:折扣|優惠券|補償|退款)",
        r"(?:give|issue|approve|offer).{0,15}(?:discount|coupon|compensation|refund)",
    )

    @staticmethod
    def _contains_unnegated(answer: str, patterns: tuple[str, ...]) -> bool:
        negation = re.compile(
            r"(?:不得|不可|不能|禁止|不應|尚未|未核准|do not|cannot|can't|must not|not authorized)",
            re.IGNORECASE,
        )
        for pattern in patterns:
            for match in re.finditer(pattern, answer, re.IGNORECASE | re.DOTALL):
                if not negation.search(answer[max(0, match.start() - 20) : match.start()]):
                    return True
        return False

    def sanitize(self, answer: str, *, identity: Identity) -> str:
        if not isinstance(answer, str):
            raise OutputGuardrailError("invalid_output", "answer must be text")
        if self._contains_unnegated(answer, self._forbidden_commitments):
            raise OutputGuardrailError(
                "guaranteed_outcome", "answer contains an unauthorized outcome guarantee"
            )
        if self._contains_unnegated(answer, self._unauthorized_offers):
            raise OutputGuardrailError(
                "unauthorized_offer", "answer contains an unapproved offer or compensation"
            )
        sanitized = redact_text(answer)
        sanitized = re.sub(
            r"(?i)\b(?:name|customer[_ ]?name|姓名|客戶姓名)\s*[:：]\s*[^,，;；\n]+",
            "姓名：[REDACTED_NAME]",
            sanitized,
        )
        if identity.role in {"PM", "Ops"}:
            sanitized = re.sub(r"\bU\d{6}\b", "[REDACTED_USER_ID]", sanitized)
        return sanitized
