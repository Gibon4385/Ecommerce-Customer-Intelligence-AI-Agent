from __future__ import annotations

from pathlib import Path

import pytest

from ecommerce_agent.auth.identity import DevIdentityProvider
from ecommerce_agent.monitoring import aggregate_interactions, export_diagnostic_bundle
from ecommerce_agent.observability.tracing import JsonlTraceStore

ROOT = Path(__file__).resolve().parents[2]


def test_admin_exports_only_redacted_diagnostic_bundle(tmp_path: Path) -> None:
    traces = JsonlTraceStore(tmp_path / "traces.jsonl")
    trace_id = traces.new_trace_id()
    traces.record(
        "input_received",
        trace_id,
        content="Customer U000001 email a@example.com password=hunter2",
    )
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    output = export_diagnostic_bundle(
        traces,
        trace_id=trace_id,
        identity=identities.resolve("admin_01", channel="diagnostics"),
        output_path=tmp_path / "bundle.json",
    )
    serialized = output.read_text(encoding="utf-8")
    for secret in ("U000001", "a@example.com", "hunter2"):
        assert secret not in serialized
    assert '"redacted": true' in serialized
    assert traces.recent()[-1]["payload"]["action"] == "export_diagnostic_bundle"


def test_non_admin_cannot_export_diagnostics(tmp_path: Path) -> None:
    traces = JsonlTraceStore(tmp_path / "traces.jsonl")
    trace_id = traces.new_trace_id()
    traces.record("event", trace_id, value="safe")
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    with pytest.raises(PermissionError, match="Admin"):
        export_diagnostic_bundle(
            traces,
            trace_id=trace_id,
            identity=identities.resolve("ops_01"),
            output_path=tmp_path / "forbidden.json",
        )
    assert not (tmp_path / "forbidden.json").exists()


@pytest.mark.parametrize(
    ("terminal", "expected"),
    [
        ("interaction_completed", "Success"),
        ("interaction_blocked", "Blocked"),
        ("interaction_failed", "Failed"),
        ("interaction_cancelled", "Cancelled"),
    ],
)
def test_interaction_summary_groups_trace_and_maps_terminal_status(
    terminal: str, expected: str
) -> None:
    events = [
        {
            "trace_id": "trace-123456789",
            "timestamp": "2026-11-05T16:30:00+00:00",
            "event_type": "interaction_started",
            "payload": {
                "channel": "mcp",
                "role": "Ops",
                "request_type": "direct_tool",
                "tool": "get_daily_kpi",
            },
        },
        {
            "trace_id": "trace-123456789",
            "timestamp": "2026-11-05T16:30:01+00:00",
            "event_type": terminal,
            "payload": {"row_count": 10, "duration_ms": 125.5, "error_type": "SafeError"},
        },
    ]
    summary = aggregate_interactions(events)
    assert len(summary) == 1
    assert summary[0]["date"] == "2026-11-06"
    assert summary[0]["time"] == "00:30:00"
    assert summary[0]["timezone"] == "Asia/Taipei"
    assert summary[0]["status"] == expected
    assert summary[0]["request"] == "查詢每日 KPI"
    assert len(summary[0]["events"]) == 2
