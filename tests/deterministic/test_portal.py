from __future__ import annotations

from pathlib import Path

import pytest

from ecommerce_agent.auth.identity import DevIdentityProvider
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.portal import PortalApp

ROOT = Path(__file__).resolve().parents[2]


def test_portal_knowledge_forms_and_fixed_identity(tmp_path: Path) -> None:
    traces = JsonlTraceStore(tmp_path / "runtime/traces.jsonl")
    identity = DevIdentityProvider(ROOT / "configs/dev_users.yaml").resolve(
        "marketing_01", channel="portal"
    )
    app = PortalApp(root=tmp_path, identity=identity, traces=traces, csrf_token="test")
    home = app.home()
    knowledge = app.knowledge_page()
    assert "marketing_01" in home and "Marketing" in home
    assert "metric_definition" in knowledge
    assert "business_policy" in knowledge
    assert "answer_playbook" in knowledge
    assert "rbac.yaml" not in knowledge and "system prompt" not in knowledge.lower()


def test_monitoring_is_admin_only_and_access_is_audited(tmp_path: Path) -> None:
    traces = JsonlTraceStore(tmp_path / "runtime/traces.jsonl")
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    denied = PortalApp(
        root=tmp_path,
        identity=identities.resolve("ops_01", channel="portal"),
        traces=traces,
    )
    with pytest.raises(PermissionError, match="Admin"):
        denied.monitoring_page()
    admin = PortalApp(
        root=tmp_path,
        identity=identities.resolve("admin_01", channel="portal"),
        traces=traces,
    )
    rendered = admin.monitoring_page()
    assert "Interaction Monitoring" in rendered
    assert "Date" in rendered and "Time" in rendered and "Asia/Taipei" in rendered
    assert "Redacted payload" in rendered
    assert traces.recent()[-1]["event_type"] == "monitoring_access"
