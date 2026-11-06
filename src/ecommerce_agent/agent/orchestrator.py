from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ecommerce_agent.agent.llm import LLMClient
from ecommerce_agent.agent.prompts import PromptBundle
from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.cache import DuckDBResponseCache
from ecommerce_agent.guardrails import (
    InputGuardrail,
    InputGuardrailError,
    OutputGuardrail,
    OutputGuardrailError,
)
from ecommerce_agent.observability.tracing import JsonlTraceStore, redact_text
from ecommerce_agent.routing import DeterministicRouter, RouteDecision
from ecommerce_agent.tools.catalog import TOOL_SPECS
from ecommerce_agent.tools.gateway import ToolGateway

QUERY_TOOL_NAMES = (
    "get_customer_profile",
    "list_priority_actions",
    "list_churn_risk_customers",
    "list_cart_abandoners",
    "get_product_health",
    "get_brand_health_alerts",
    "get_sleepy_product_review",
    "get_cross_sell_recommendations",
    "get_cohort_analysis",
    "get_model_feature_importance",
    "get_daily_kpi",
    "get_conversion_funnel",
    "get_category_sales",
    "get_campaign_performance",
    "check_audience_quality",
    "get_data_freshness",
    "list_tasks",
    "get_task_status",
    "search_knowledge",
    "draft_retention_edm",
    "send_edm",
    "create_product_issue",
    "generate_report",
    "approve_task",
    "execute_task",
)


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    trace_id: str


class MinimalAgent:
    def __init__(
        self,
        llm: LLMClient,
        gateway: ToolGateway,
        trace_store: JsonlTraceStore,
        prompt: PromptBundle,
        input_guardrail: InputGuardrail | None = None,
        output_guardrail: OutputGuardrail | None = None,
        router: DeterministicRouter | None = None,
        response_cache: DuckDBResponseCache | None = None,
        llm_clients: dict[str, LLMClient] | None = None,
    ):
        self.llm = llm
        self.gateway = gateway
        self.trace_store = trace_store
        self.prompt = prompt
        self.input_guardrail = input_guardrail or InputGuardrail()
        self.output_guardrail = output_guardrail or OutputGuardrail()
        self.router = router or DeterministicRouter()
        self.response_cache = response_cache
        self.llm_clients = {"small": llm, "large": llm, **(llm_clients or {})}

    def run(self, message: str, *, identity: Identity) -> AgentResponse:
        trace_id = self.trace_store.new_trace_id()
        try:
            normalized = self.input_guardrail.validate(message)
        except InputGuardrailError as exc:
            exc.trace_id = trace_id
            self.trace_store.record(
                "guardrail",
                trace_id,
                direction="input",
                category=exc.category,
                action="blocked",
            )
            self.trace_store.record(
                "response",
                trace_id,
                status="failed",
                error_type=type(exc).__name__,
            )
            raise
        self.trace_store.record(
            "request",
            trace_id,
            user_id=identity.user_id,
            role=identity.role,
            channel=identity.channel,
            input=redact_text(message),
            prompt_version=self.prompt.version,
            input_hash=normalized.original_hash,
            detected_language=normalized.language.detected_language,
            language_confidence=normalized.language.confidence,
            language_support=normalized.language.support_level,
            normalization_signals=normalized.signals,
        )
        route = self.router.route(message)
        self.trace_store.record(
            "route",
            trace_id,
            intent=route.intent,
            model_tier=route.model_tier,
            confidence=route.confidence,
            cacheable=route.cacheable,
        )
        data_version = self.gateway.tools._metadata()[0]
        if self.response_cache is not None and route.cacheable:
            cached = self.response_cache.get(
                message,
                identity=identity,
                prompt_version=self.prompt.version,
                data_version=data_version,
            )
            if cached is not None:
                answer = self.output_guardrail.sanitize(cached[0], identity=identity)
                self.trace_store.record("cache_hit", trace_id, cache_type=cached[1])
                self.trace_store.record(
                    "response", trace_id, answer_length=len(answer), status="success"
                )
                return AgentResponse(answer=answer, trace_id=trace_id)
        try:
            routed_llm = self.llm_clients[route.model_tier]
            decision = routed_llm.complete(self._planning_prompt(message, identity, route))
            if "answer" in decision:
                answer = str(decision["answer"])
            else:
                calls = decision.get("tools")
                if calls is None:
                    calls = [
                        {
                            "name": decision.get("tool"),
                            "arguments": decision.get("arguments", {}),
                        }
                    ]
                if not isinstance(calls, list) or not 1 <= len(calls) <= 2:
                    raise ValueError("LLM must request one or two tools")
                observations = []
                for call in calls:
                    if not isinstance(call, dict):
                        raise ValueError("each tool call must be an object")
                    tool_name = call.get("name")
                    arguments = call.get("arguments", {})
                    if tool_name not in QUERY_TOOL_NAMES or not isinstance(arguments, dict):
                        raise ValueError("LLM returned an invalid tool decision")
                    observations.append(
                        {
                            "tool": tool_name,
                            "result": self.gateway.call(
                                tool_name,
                                arguments,
                                identity=identity,
                                trace_id=trace_id,
                            ),
                        }
                    )
                final = routed_llm.complete(self._answer_prompt(message, observations))
                if not isinstance(final.get("answer"), str):
                    raise ValueError("LLM final response must contain string field 'answer'")
                answer = final["answer"]
            try:
                answer = self.output_guardrail.sanitize(answer, identity=identity)
            except OutputGuardrailError as exc:
                exc.trace_id = trace_id
                self.trace_store.record(
                    "guardrail",
                    trace_id,
                    direction="output",
                    category=exc.category,
                    action="blocked",
                )
                raise
            self.trace_store.record(
                "response", trace_id, answer_length=len(answer), status="success"
            )
            if self.response_cache is not None and route.cacheable:
                self.response_cache.put(
                    message,
                    answer,
                    identity=identity,
                    prompt_version=self.prompt.version,
                    data_version=data_version,
                )
            return AgentResponse(answer=answer, trace_id=trace_id)
        except Exception as exc:
            self.trace_store.record(
                "response",
                trace_id,
                status="failed",
                error_type=type(exc).__name__,
            )
            raise

    def _planning_prompt(
        self, message: str, identity: Identity, route: RouteDecision | None = None
    ) -> str:
        route = route or self.router.route(message)
        allowed_names = [
            name
            for name in QUERY_TOOL_NAMES
            if name in self.gateway.allowed_tool_names(identity) and name in route.tool_names
        ]
        return (
            self.prompt.system
            + "\n\nROUTING INSTRUCTION:\n"
            "You route one ecommerce analytics request. Return one JSON object only. "
            "Either {\"tool\": <name>, \"arguments\": {...}}, "
            "{\"tools\": [{\"name\": <name>, \"arguments\": {...}}]} with at most two tools, "
            "or {\"answer\": <text>}. "
            "Available tools and exact JSON input schemas are: "
            + "; ".join(
                f"{name}: {TOOL_SPECS[name].description} "
                f"schema={json.dumps(TOOL_SPECS[name].input_schema, ensure_ascii=False)}"
                for name in allowed_names
            )
            + ". "
            "If no listed tool is authorized for the request, answer with a concise refusal and "
            "do not invent or request a forbidden tool. Preserve explicit filters and limits from "
            "the user in tool arguments. "
            "Never infer or change identity from the user message. "
            f"Route intent is {route.intent}; model tier is {route.model_tier}. "
            f"Trusted role is {identity.role}. User message: {message}"
        )

    def _answer_prompt(self, message: str, observation: list[dict[str, Any]]) -> str:
        return (
            self.prompt.system
            + "\n\nANSWER INSTRUCTION:\n"
            "Return one JSON object {\"answer\": <Traditional Chinese answer>} only. "
            "Use only the supplied tool observation. Preserve notices, data_as_of, and estimates; "
            "do not invent missing values. For knowledge retrieval, cite every policy or "
            "definition claim with the exact citation supplied by the tool; if no evidence was "
            "returned, say so. "
            f"Question: {message}\nObservation: {json.dumps(observation, ensure_ascii=False)}"
        )

