from __future__ import annotations

from pathlib import Path

from ecommerce_agent.cli import build_runtime
from ecommerce_agent.dashboard import generate_dashboard

ROOT = Path(__file__).resolve().parents[2]


def test_ops_dashboard_uses_gateway_and_fixed_html(tmp_path: Path) -> None:
    identities, gateway, traces = build_runtime(ROOT)
    output = tmp_path / "ops.html"
    result = generate_dashboard(
        gateway,
        traces,
        identity=identities.resolve("ops_01", channel="dashboard"),
        output_path=output,
    )
    rendered = output.read_text(encoding="utf-8")
    assert result.output_path == output
    assert "get_daily_kpi" in rendered and "list_tasks" in rendered
    assert "completed orders only" in rendered
    assert "<script" not in rendered.lower()
    events = traces.get(result.trace_id)
    assert events[0]["event_type"] == "interaction_started"
    assert events[-1]["event_type"] == "interaction_completed"


def test_support_dashboard_does_not_render_unauthorized_analytics(tmp_path: Path) -> None:
    identities, gateway, traces = build_runtime(ROOT)
    output = tmp_path / "support.html"
    generate_dashboard(
        gateway,
        traces,
        identity=identities.resolve("support_01", channel="dashboard"),
        output_path=output,
    )
    rendered = output.read_text(encoding="utf-8")
    assert "get_data_freshness" in rendered and "list_tasks" in rendered
    assert "get_daily_kpi" not in rendered
    assert "[REDACTED_IDENTIFIER]" not in rendered
