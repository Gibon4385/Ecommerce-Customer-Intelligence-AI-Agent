from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ecommerce_agent.agent.llm import CliLLMClient
from ecommerce_agent.agent.orchestrator import MinimalAgent
from ecommerce_agent.agent.prompts import load_system_prompt
from ecommerce_agent.cli import build_runtime
from ecommerce_agent.evaluation import evaluate_records, load_golden_set
from ecommerce_agent.guardrails import (
    SAFE_BLOCKED_MESSAGE,
    InputGuardrailError,
    OutputGuardrailError,
)

ROOT = Path(__file__).resolve().parents[1]


class RecordingClient:
    def __init__(self, delegate: CliLLMClient):
        self.delegate = delegate
        self.responses: list[dict[str, Any]] = []

    def complete(self, prompt: str) -> dict[str, Any]:
        response = self.delegate.complete(prompt)
        self.responses.append(response)
        return response


def _calls(decision: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not decision or "answer" in decision:
        return []
    if "tools" in decision:
        return decision["tools"]
    return [{"name": decision.get("tool"), "arguments": decision.get("arguments", {})}]


def run(limit: int | None, model: str | None, timeout: float) -> dict[str, Any]:
    metadata, cases = load_golden_set(ROOT / "evals/golden_set_v0.json")
    if limit is not None:
        cases = cases[:limit]
    identities, gateway, traces = build_runtime(ROOT)
    prompt = load_system_prompt(ROOT / "prompts/system_v1.md")
    records = []
    command = ["codex", "exec", "--ephemeral", "--json"]
    if model:
        command += ["--model", model]
    command.append("-")
    for case in cases:
        client = RecordingClient(
            CliLLMClient(command=tuple(command), timeout_seconds=timeout)
        )
        agent = MinimalAgent(client, gateway, traces, prompt)
        answer = None
        error = None
        trace_id = None
        try:
            response = agent.run(case.question, identity=identities.resolve(case.user_id))
            answer, trace_id = response.answer, response.trace_id
        except (InputGuardrailError, OutputGuardrailError) as exc:
            answer = SAFE_BLOCKED_MESSAGE
            trace_id = exc.trace_id
        except Exception as exc:  # report per-case failure and continue the baseline
            error = f"{type(exc).__name__}: {exc}"
        decision = client.responses[0] if client.responses else None
        records.append(
            {
                "id": case.id,
                "calls": _calls(decision),
                "answer": answer,
                "error": error,
                "trace_id": trace_id,
            }
        )
        print(f"{case.id}: {'error' if error else 'complete'}")
    scoring = evaluate_records(cases, records)
    version = subprocess.run(
        ["codex", "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "golden_version": metadata["version"],
        "prompt_version": prompt.version,
        "cli_version": version or "unavailable",
        "model": model or "Codex CLI default (exact model unavailable)",
        "token_usage": "CLI mode unavailable",
        "cost": "CLI mode unavailable",
        "records": records,
        "scoring": scoring,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument(
        "--output", default="reports/verification/golden_v0_baseline.json"
    )
    args = parser.parse_args()
    report = run(args.limit, args.model, args.timeout)
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["scoring"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

