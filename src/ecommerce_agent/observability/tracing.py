from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
    return re.sub(r"\b[a-fA-F0-9]{64}\b", "[REDACTED_HASH]", value)


def redact_value(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if lowered == "input_hash" and isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
        # This is a request-content digest for correlation, not a customer identifier.
        return value
    if lowered in {"email", "hashed_email", "user_id", "requested_by", "approved_by"}:
        return "[REDACTED_IDENTIFIER]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {item_key: redact_value(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, key) for item in value]
    return value


@dataclass
class TraceEvent:
    event_type: str
    trace_id: str
    timestamp: str = field(default_factory=_now)
    payload: dict[str, Any] = field(default_factory=dict)


class JsonlTraceStore:
    def __init__(self, path: Path):
        self.path = path
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
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False, default=str) + "\n")

    def get(self, trace_id: str) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line and json.loads(line)["trace_id"] == trace_id
        ]

