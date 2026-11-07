from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.observability.tracing import (
    JsonlTraceStore,
    redact_value,
    redacted_content_record,
)

from .catalog import TOOL_SPECS
from .query import QueryTools, ToolResult, json_safe


class ToolAuthorizationError(PermissionError):
    pass


class ToolNotFoundError(LookupError):
    pass


class ToolGateway:
    def __init__(
        self,
        tools: QueryTools,
        rbac_path: Path,
        trace_store: JsonlTraceStore,
    ):
        self.tools = tools
        self.roles = yaml.safe_load(rbac_path.read_text(encoding="utf-8"))["roles"]
        self.trace_store = trace_store

    def allowed_tool_names(self, identity: Identity) -> list[str]:
        allowed = self.roles.get(identity.role, {}).get("tools", [])
        if "*" in allowed:
            return sorted(TOOL_SPECS)
        return list(allowed)

    def _enforce_parameter_limits(
        self, identity: Identity, tool_name: str, arguments: dict[str, Any]
    ) -> None:
        configured = self.roles.get(identity.role, {}).get("max_limits", {}).get(tool_name)
        requested = arguments.get("limit", arguments.get("top_k"))
        if configured is not None and requested is not None and requested > configured:
            raise ToolAuthorizationError(
                f"role {identity.role} limit for {tool_name} is {configured}"
            )

    def _enforce_data_scope(
        self, identity: Identity, tool_name: str, arguments: dict[str, Any]
    ) -> None:
        if identity.data_scope != "single_customer":
            return
        if "user_ids" in arguments:
            raise ToolAuthorizationError("single_customer scope cannot request multiple users")
        if tool_name == "get_customer_profile" and not isinstance(
            arguments.get("user_id"), str
        ):
            raise ToolAuthorizationError("single_customer scope requires one user_id")

    def _mask(self, value: Any, denied: set[str]) -> Any:
        if isinstance(value, dict):
            return {
                key: self._mask(item, denied)
                for key, item in value.items()
                if key not in denied
            }
        if isinstance(value, list):
            return [self._mask(item, denied) for item in value]
        return value

    def call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        identity: Identity,
        trace_id: str,
    ) -> dict[str, Any]:
        method = getattr(self.tools, tool_name, None)
        if not callable(method) or tool_name.startswith("_"):
            raise ToolNotFoundError(tool_name)
        allowed = self.allowed_tool_names(identity)
        authorized = tool_name in allowed
        self.trace_store.record(
            "authorization",
            trace_id,
            user_id=identity.user_id,
            role=identity.role,
            tool=tool_name,
            allowed=authorized,
            arguments=redact_value(arguments),
        )
        if not authorized:
            raise ToolAuthorizationError(f"role {identity.role} cannot use {tool_name}")
        self._enforce_parameter_limits(identity, tool_name, arguments)
        self._enforce_data_scope(identity, tool_name, arguments)
        started = time.monotonic()
        try:
            call_arguments = dict(arguments)
            if tool_name in {
                "list_tasks",
                "get_task_status",
                "search_knowledge",
                "draft_retention_edm",
                "prepare_send_edm",
                "prepare_product_issue",
                "prepare_report",
                "approve_task",
                "execute_task",
                "send_edm",
                "create_product_issue",
                "generate_report",
            }:
                call_arguments["identity"] = identity
            if tool_name in {
                "draft_retention_edm",
                "prepare_send_edm",
                "prepare_product_issue",
                "prepare_report",
                "approve_task",
                "execute_task",
                "send_edm",
                "create_product_issue",
                "generate_report",
            }:
                call_arguments["trace_id"] = trace_id
            result: ToolResult = method(**call_arguments)
        except Exception as exc:
            self.trace_store.record(
                "tool_error",
                trace_id,
                tool=tool_name,
                error_type=type(exc).__name__,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
            raise
        payload = json_safe(asdict(result))
        denied = set(self.roles.get(identity.role, {}).get("deny_fields", []))
        payload = self._mask(payload, denied)
        self.trace_store.record(
            "tool_result",
            trace_id,
            tool=tool_name,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            row_count=len(result.data) if isinstance(result.data, list) else None,
            data_version=result.data_version,
            data_as_of=result.data_as_of,
            output=redacted_content_record(
                json.dumps(redact_value(payload), ensure_ascii=False, default=str)
            ),
            citations=(
                [row.get("citation") for row in payload.get("data", []) if row.get("citation")]
                if tool_name == "search_knowledge" and isinstance(payload.get("data"), list)
                else []
            ),
        )
        return payload

