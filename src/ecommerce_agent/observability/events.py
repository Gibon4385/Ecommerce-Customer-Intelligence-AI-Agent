from __future__ import annotations

from enum import StrEnum

TRACE_SCHEMA_VERSION = "1.0"


class InteractionStatus(StrEnum):
    SUCCESS = "success"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_EVENT_TYPES: dict[InteractionStatus, str] = {
    InteractionStatus.SUCCESS: "interaction_completed",
    InteractionStatus.BLOCKED: "interaction_blocked",
    InteractionStatus.FAILED: "interaction_failed",
    InteractionStatus.CANCELLED: "interaction_cancelled",
}
