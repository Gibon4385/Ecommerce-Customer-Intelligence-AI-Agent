from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .events import TRACE_SCHEMA_VERSION

_RESTRICTED_KEYS = {
    "approved_by",
    "authorization",
    "cookie",
    "email",
    "hashed_email",
    "password",
    "requested_by",
    "secret",
    "set_cookie",
    "token",
    "user_id",
}
_RESTRICTED_KEY_PARTS = ("api_key", "credential", "private_key", "access_token", "refresh_token")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def redact_text(value: str) -> str:
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", value)
    value = re.sub(
        r"(?!\d{4}-\d{2}-\d{2}\b)(?<!\w)(?:\+?\d[\d -]{7,}\d)(?!\w)",
        "[REDACTED_PHONE]",
        value,
    )
    value = re.sub(r"\bU\d{6}\b", "[REDACTED_USER_ID]", value)
    value = re.sub(r"\b[a-fA-F0-9]{64}\b", "[REDACTED_HASH]", value)
    value = re.sub(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+", "Bearer [REDACTED_SECRET]", value)
    value = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
        r"\s*[:=]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=[REDACTED_SECRET]",
        value,
    )
    value = re.sub(
        r"(?i)\b(?:name|customer[_ ]?name|姓名|客戶姓名)\s*[:：]\s*[^,，;；\n]+",
        "姓名：[REDACTED_NAME]",
        value,
    )
    return value


def redact_value(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if (
        lowered in {"input_hash", "content_hash"}
        and isinstance(value, str)
        and re.fullmatch(r"[a-f0-9]{64}", value)
    ):
        # These are server-generated content digests, not customer identifiers.
        return value
    if lowered in _RESTRICTED_KEYS or any(part in lowered for part in _RESTRICTED_KEY_PARTS):
        return (
            "[REDACTED_SECRET]"
            if lowered
            not in {
                "email",
                "hashed_email",
                "user_id",
                "requested_by",
                "approved_by",
            }
            else "[REDACTED_IDENTIFIER]"
        )
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {item_key: redact_value(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, key) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item, key) for item in value)
    return value


def redacted_content_record(value: str, *, max_characters: int = 20_000) -> dict[str, Any]:
    redacted = redact_text(value)
    truncated = len(redacted) > max_characters
    stored = redacted[:max_characters] if truncated else redacted
    return {
        "content_redacted": stored,
        "content_hash": hashlib.sha256(redacted.encode("utf-8")).hexdigest(),
        "characters": len(redacted),
        "truncated": truncated,
    }


@dataclass
class TraceEvent:
    event_type: str
    trace_id: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = TRACE_SCHEMA_VERSION
    timestamp: str = field(default_factory=_now)
    payload: dict[str, Any] = field(default_factory=dict)


class JsonlTraceStore:
    def __init__(self, path: Path, *, max_file_bytes: int = 5_000_000):
        self.path = path
        self.max_file_bytes = max_file_bytes
        self._lock = threading.Lock()

    def new_trace_id(self) -> str:
        return str(uuid.uuid4())

    def record(self, event_type: str, trace_id: str, **payload: Any) -> None:
        event = TraceEvent(
            event_type=event_type,
            trace_id=trace_id,
            payload=redact_value(payload),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(asdict(event), ensure_ascii=False, default=str) + "\n"
        with self._lock:
            if (
                self.path.exists()
                and self.path.stat().st_size + len(serialized.encode("utf-8")) > self.max_file_bytes
            ):
                self.path.replace(self.path.with_suffix(self.path.suffix + ".1"))
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(serialized)

    def get(self, trace_id: str) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line and json.loads(line)["trace_id"] == trace_id
        ]

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        paths = [self.path.with_suffix(self.path.suffix + ".1"), self.path]
        events: list[dict[str, Any]] = []
        for path in paths:
            if path.is_file():
                events.extend(
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line
                )
        return events[-limit:]
