from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.observability.tracing import JsonlTraceStore

DISPLAY_TIMEZONE = "Asia/Taipei"
TERMINAL_STATUS = {
    "interaction_completed": "Success",
    "interaction_blocked": "Blocked",
    "interaction_failed": "Failed",
    "interaction_cancelled": "Cancelled",
}
REQUEST_LABELS = {
    "natural_language": "處理自然語言查詢",
    "workflow": "執行每日營運晨報",
    "dashboard_snapshot": "產生營運儀表板快照",
}
TOOL_LABELS = {"get_daily_kpi": "查詢每日 KPI"}


def _local_parts(timestamp: str) -> tuple[str, str]:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    local = parsed.astimezone(ZoneInfo(DISPLAY_TIMEZONE))
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M:%S")


def _request_summary(events: list[dict[str, Any]]) -> str:
    payloads = [event.get("payload", {}) for event in events]
    tool = next((item.get("tool") for item in payloads if item.get("tool")), None)
    if tool:
        return TOOL_LABELS.get(str(tool), f"執行工具 {tool}")
    request_type = next(
        (item.get("request_type") for item in payloads if item.get("request_type")), None
    )
    return REQUEST_LABELS.get(str(request_type), "處理互動請求")


def _result_summary(terminal: dict[str, Any] | None) -> str:
    if terminal is None:
        return "尚未完成"
    payload = terminal.get("payload", {})
    event_type = terminal["event_type"]
    if event_type == "interaction_completed":
        row_count = payload.get("row_count")
        return f"成功，回傳 {row_count} rows" if row_count is not None else "成功完成"
    if event_type == "interaction_blocked":
        if payload.get("category") == "prompt_injection":
            return "輸入被安全規則阻擋"
        return "請求被安全規則或權限阻擋"
    if event_type == "interaction_failed":
        error = payload.get("error_type") or "UnknownError"
        return f"執行失敗；{error}"
    return "互動已取消"


def aggregate_interactions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for event in sorted(events, key=lambda item: str(item.get("timestamp", "")), reverse=True):
        grouped.setdefault(str(event["trace_id"]), []).append(event)
    summaries: list[dict[str, Any]] = []
    for trace_id, trace_events in grouped.items():
        chronological = sorted(trace_events, key=lambda item: str(item["timestamp"]))
        terminal = next(
            (event for event in reversed(chronological) if event["event_type"] in TERMINAL_STATUS),
            None,
        )
        first = chronological[0]
        date, time = _local_parts(str(first["timestamp"]))
        payloads = [event.get("payload", {}) for event in chronological]
        duration = next(
            (
                item.get("duration_ms")
                for item in reversed(payloads)
                if item.get("duration_ms") is not None
            ),
            None,
        )
        status = (
            TERMINAL_STATUS.get(terminal["event_type"], "In progress")
            if terminal
            else "In progress"
        )
        channel = next(
            (str(item["channel"]) for item in payloads if item.get("channel")), "Unknown"
        )
        role = next(
            (str(item["role"]) for item in payloads if item.get("role")), "Unknown"
        )
        summaries.append(
            {
                "trace_id": trace_id,
                "date": date,
                "time": time,
                "timezone": DISPLAY_TIMEZONE,
                "status": status,
                "channel": channel,
                "role": role,
                "request": _request_summary(chronological),
                "result": _result_summary(terminal),
                "duration": f"{float(duration):.1f} ms" if duration is not None else "Unknown",
                "events": chronological,
            }
        )
    return summaries


def export_diagnostic_bundle(
    traces: JsonlTraceStore,
    *,
    trace_id: str,
    identity: Identity,
    output_path: Path,
) -> Path:
    if identity.role != "Admin":
        raise PermissionError("diagnostic export requires Admin")
    events = traces.get(trace_id)
    if not events:
        raise LookupError("trace not found")
    bundle = {
        "schema_version": "1.0",
        "trace_id": trace_id,
        "events": events,
        "redacted": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    audit_trace = traces.new_trace_id()
    traces.record(
        "monitoring_access",
        audit_trace,
        role=identity.role,
        channel=identity.channel,
        action="export_diagnostic_bundle",
        exported_trace_id=trace_id,
        output_path=str(output_path),
    )
    return output_path


def main(argv: list[str] | None = None) -> int:
    from ecommerce_agent.cli import build_runtime

    parser = argparse.ArgumentParser(prog="ecommerce-agent-diagnostics")
    parser.add_argument("--as", dest="user_id", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    identities, _, traces = build_runtime()
    identity = identities.resolve(args.user_id, channel="diagnostics")
    path = export_diagnostic_bundle(
        traces, trace_id=args.trace, identity=identity, output_path=args.output
    )
    print(json.dumps({"output": str(path), "redacted": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
