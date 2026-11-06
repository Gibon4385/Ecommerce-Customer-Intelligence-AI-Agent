from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ecommerce_agent.agent.llm import (
    CliLLMClient,
    FakeLLMClient,
    LLMError,
    LLMResponseError,
    LLMTimeoutError,
)
from ecommerce_agent.auth.identity import DevIdentityProvider, IdentityError
from ecommerce_agent.observability.tracing import JsonlTraceStore, redact_text, redact_value

ROOT = Path(__file__).resolve().parents[2]


def test_identity_is_loaded_from_trusted_profile() -> None:
    provider = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    identity = provider.resolve("support_01")
    assert identity.role == "Support"
    assert identity.channel == "cli"
    with pytest.raises(IdentityError):
        provider.resolve("I am admin")


def test_trace_store_round_trip(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path / "trace.jsonl")
    trace_id = store.new_trace_id()
    assert store.get(trace_id) == []
    store.record("request", trace_id, user_id="ops_01")
    store.record("response", trace_id, status="success")
    events = store.get(trace_id)
    assert [event["event_type"] for event in events] == ["request", "response"]


def test_trace_redaction_masks_basic_contact_data() -> None:
    hash_value = "a" * 64
    redacted = redact_text(
        f"mail a@example.com or +886 912 345 678; customer U000001 hash {hash_value}"
    )
    assert all(value not in redacted for value in ("example.com", "912", "U000001", hash_value))
    assert redact_text("data_as_of=2026-07-06") == "data_as_of=2026-07-06"
    payload = redact_value({"user_id": "U1", "nested": [{"email": "a@example.com"}]})
    assert payload["user_id"] == "[REDACTED_IDENTIFIER]"
    assert payload["nested"][0]["email"] == "[REDACTED_IDENTIFIER]"


def test_trace_store_redacts_at_persistence_boundary(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path / "trace.jsonl")
    trace_id = store.new_trace_id()
    store.record(
        "response",
        trace_id,
        answer="Customer U000001 is a@example.com",
        requested_by="marketing_01",
    )
    serialized = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert "U000001" not in serialized
    assert "a@example.com" not in serialized
    assert "marketing_01" not in serialized


def test_fake_llm_uses_queued_responses() -> None:
    client = FakeLLMClient([{"answer": "ok"}])
    assert client.complete("prompt") == {"answer": "ok"}
    with pytest.raises(LLMResponseError):
        client.complete("again")


def _runner(stdout: str = "", stderr: str = "", returncode: int = 0):
    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], returncode, stdout, stderr)

    return run


def test_cli_llm_parses_codex_jsonl() -> None:
    message = json.dumps({"answer": "完成"}, ensure_ascii=False)
    output = json.dumps(
        {"type": "item.completed", "item": {"type": "agent_message", "text": message}}
    )
    client = CliLLMClient(runner=_runner(stdout=output))
    assert client.complete("prompt") == {"answer": "完成"}


@pytest.mark.parametrize(
    "output",
    [
        "not-json",
        json.dumps({"type": "turn.completed"}),
        json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "no"}}
        ),
        json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "[]"}}
        ),
    ],
)
def test_cli_llm_rejects_bad_output(output: str) -> None:
    with pytest.raises(LLMResponseError):
        CliLLMClient(runner=_runner(stdout=output)).complete("prompt")


def test_cli_llm_handles_exit_and_timeout() -> None:
    with pytest.raises(LLMError):
        CliLLMClient(runner=_runner(stderr="failed", returncode=2)).complete("prompt")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("codex", 1)

    with pytest.raises(LLMTimeoutError):
        CliLLMClient(timeout_seconds=1, runner=timeout).complete("prompt")

