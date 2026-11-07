from __future__ import annotations

import argparse
import html
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.tools.gateway import ToolGateway


@dataclass(frozen=True)
class DashboardResult:
    output_path: Path
    trace_id: str
    sections: tuple[str, ...]


_QUERIES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("get_data_freshness", {}),
    ("get_daily_kpi", {"limit": 7}),
    ("get_conversion_funnel", {"category": "ALL", "limit": 30}),
    ("get_category_sales", {"limit": 20}),
    ("get_brand_health_alerts", {}),
    ("list_tasks", {"limit": 20}),
)


def _table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty">目前沒有可顯示的資料。</p>'
    columns = list(rows[0])
    head = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        f"{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _render(identity: Identity, results: dict[str, dict[str, Any]], trace_id: str) -> str:
    cards = []
    for name, result in results.items():
        data = result.get("data")
        rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        notices = "".join(
            f"<li>{html.escape(str(item))}</li>" for item in result.get("notices", [])
        )
        cards.append(
            f"<section><h2>{html.escape(name)}</h2>"
            f"<p class=\"meta\">data-as-of: {html.escape(str(result.get('data_as_of')))} · "
            f"version: {html.escape(str(result.get('data_version')))}</p>"
            f"{_table(rows)}<ul>{notices}</ul></section>"
        )
    return """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ecommerce Operations Snapshot</title>
<style>
body { font-family: system-ui, sans-serif; margin: 0; background: #f4f6f8; color: #17212b; }
header { background: #17324d; color: white; padding: 28px; }
main { max-width: 1200px; margin: auto; padding: 24px; display: grid; gap: 20px; }
section { background: white; border: 1px solid #d9e0e7; border-radius: 12px; padding: 20px; }
.meta { color: #52616f; font-size: .9rem; }
.table-wrap { overflow: auto; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { border-bottom: 1px solid #e5e9ed; padding: 8px; text-align: left; white-space: nowrap; }
th { background: #eef3f7; }
.empty { color: #6a7783; }
footer { padding: 24px; text-align: center; color: #667; }
</style></head><body>""" + (
        f"<header><h1>營運與任務快照</h1><p>{html.escape(identity.user_id)} · "
        f"{html.escape(identity.role)} · {html.escape(identity.data_scope)}</p>"
        f"<p>trace: {html.escape(trace_id)}</p></header><main>{''.join(cards)}</main>"
        "<footer>固定版型 · 唯讀 · 所有資料皆經 ToolGateway</footer></body></html>"
    )


def generate_dashboard(
    gateway: ToolGateway,
    traces: JsonlTraceStore,
    *,
    identity: Identity,
    output_path: Path,
) -> DashboardResult:
    trace_id = traces.new_trace_id()
    started = time.monotonic()
    traces.record(
        "interaction_started",
        trace_id,
        channel=identity.channel,
        request_type="dashboard_snapshot",
        role=identity.role,
        data_scope=identity.data_scope,
    )
    allowed = set(gateway.allowed_tool_names(identity))
    results: dict[str, dict[str, Any]] = {}
    try:
        for tool_name, arguments in _QUERIES:
            if tool_name in allowed:
                results[tool_name] = gateway.call(
                    tool_name, arguments, identity=identity, trace_id=trace_id
                )
        rendered = _render(identity, results, trace_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        traces.record(
            "dashboard_snapshot",
            trace_id,
            output_path=str(output_path),
            sections=list(results),
            bytes=len(rendered.encode("utf-8")),
        )
        traces.record(
            "interaction_completed",
            trace_id,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        return DashboardResult(output_path, trace_id, tuple(results))
    except Exception as exc:
        traces.record(
            "interaction_failed",
            trace_id,
            error_type=type(exc).__name__,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ecommerce-agent-dashboard")
    result.add_argument("--as", dest="user_id", required=True)
    result.add_argument("--output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    from ecommerce_agent.cli import ROOT, build_runtime

    args = parser().parse_args(argv)
    identities, gateway, traces = build_runtime()
    identity = identities.resolve(args.user_id, channel="dashboard")
    output = args.output or ROOT / "runtime/dashboard" / args.user_id / "index.html"
    result = generate_dashboard(gateway, traces, identity=identity, output_path=output)
    print(json.dumps({"dashboard": str(result.output_path), "trace_id": result.trace_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
