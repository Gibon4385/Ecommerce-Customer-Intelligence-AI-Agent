from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ecommerce_agent.actions.adapters import AdapterError, MockExternalAdapter
from ecommerce_agent.actions.service import ActionService
from ecommerce_agent.agent.llm import CliLLMClient
from ecommerce_agent.agent.orchestrator import MinimalAgent
from ecommerce_agent.agent.prompts import load_system_prompt
from ecommerce_agent.auth.identity import DevIdentityProvider
from ecommerce_agent.cache import DuckDBResponseCache
from ecommerce_agent.data.repository import CsvMartRepository
from ecommerce_agent.guardrails import (
    SAFE_BLOCKED_MESSAGE,
    InputGuardrailError,
    OutputGuardrailError,
)
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.rag.store import DuckDBRagStore
from ecommerce_agent.tasks.store import DuckDBTaskStore, TaskError
from ecommerce_agent.tools.gateway import ToolAuthorizationError, ToolGateway
from ecommerce_agent.tools.query import QueryTools
from ecommerce_agent.workflows import DailyOperationsWorkflow

ROOT = Path(__file__).resolve().parents[2]


def build_runtime(root: Path = ROOT) -> tuple[DevIdentityProvider, ToolGateway, JsonlTraceStore]:
    repository = CsvMartRepository(root / "data", root / "data/schema.yml")
    traces = JsonlTraceStore(root / "runtime/traces.jsonl")
    task_store = DuckDBTaskStore(root / "runtime/agent_tasks.duckdb")
    rag_store = DuckDBRagStore(root / "runtime/knowledge.duckdb")
    rag_store.rebuild_from_manifest(root / "configs/rag_sources.yaml", root=root)
    adapter = MockExternalAdapter(
        root / "runtime/mock_external.duckdb",
        artifact_dir=root / "runtime/mock_external",
    )
    action_service = ActionService(task_store, adapter, traces)
    gateway = ToolGateway(
        QueryTools(repository, task_store, rag_store, action_service),
        root / "configs/rbac.yaml",
        traces,
    )
    identities = DevIdentityProvider(root / "configs/dev_users.yaml")
    return identities, gateway, traces


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ecommerce-agent")
    result.add_argument("--as", dest="user_id", required=True, help="trusted dev user profile")
    group = result.add_mutually_exclusive_group(required=True)
    group.add_argument("--ask", help="natural-language question routed through Codex CLI")
    group.add_argument("--tool", help="invoke a typed query tool directly")
    group.add_argument(
        "--workflow", choices=["daily-report"], help="run a deterministic workflow"
    )
    result.add_argument("--arguments", default="{}", help="JSON object for --tool")
    result.add_argument("--timeout", type=float, default=120)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    identities, gateway, traces = build_runtime()
    identity = identities.resolve(args.user_id)
    if args.workflow == "daily-report":
        workflow_result = DailyOperationsWorkflow(gateway, traces).run(identity=identity)
        print(
            json.dumps(
                {
                    "trace_id": workflow_result.trace_id,
                    "report_task_id": workflow_result.report_task_id,
                    "delayed": workflow_result.delayed,
                    "markdown": workflow_result.markdown,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.tool:
        arguments: Any = json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise SystemExit("--arguments must be a JSON object")
        trace_id = traces.new_trace_id()
        traces.record(
            "request",
            trace_id,
            user_id=identity.user_id,
            role=identity.role,
            channel=identity.channel,
            input=f"direct tool: {args.tool}",
        )
        try:
            tool_result = gateway.call(
                args.tool, arguments, identity=identity, trace_id=trace_id
            )
        except (TaskError, AdapterError, ToolAuthorizationError) as exc:
            traces.record(
                "response", trace_id, status="failed", error_type=type(exc).__name__
            )
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "message": "Action was not executed.",
                        "trace_id": trace_id,
                    },
                    ensure_ascii=False,
                )
            )
            return 2
        traces.record("response", trace_id, status="success")
        print(json.dumps({"trace_id": trace_id, "result": tool_result}, ensure_ascii=False))
        return 0
    prompt = load_system_prompt(ROOT / "prompts/system_v1.md")
    response_cache = DuckDBResponseCache(ROOT / "runtime/response_cache.duckdb")
    agent = MinimalAgent(
        CliLLMClient(timeout_seconds=args.timeout),
        gateway,
        traces,
        prompt,
        response_cache=response_cache,
    )
    try:
        response = agent.run(args.ask, identity=identity)
    except (InputGuardrailError, OutputGuardrailError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "category": exc.category,
                    "message": SAFE_BLOCKED_MESSAGE,
                    "trace_id": exc.trace_id,
                },
                ensure_ascii=False,
            )
        )
        return 2
    print(response.answer)
    print(f"trace_id={response.trace_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

