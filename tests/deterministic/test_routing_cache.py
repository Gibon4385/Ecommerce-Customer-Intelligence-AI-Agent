from __future__ import annotations

from pathlib import Path

from ecommerce_agent.agent.llm import FakeLLMClient
from ecommerce_agent.agent.orchestrator import MinimalAgent
from ecommerce_agent.agent.prompts import PromptBundle
from ecommerce_agent.auth.identity import DevIdentityProvider
from ecommerce_agent.cache import DuckDBResponseCache
from ecommerce_agent.data.repository import CsvMartRepository
from ecommerce_agent.observability.tracing import JsonlTraceStore
from ecommerce_agent.routing import DeterministicRouter
from ecommerce_agent.tools.gateway import ToolGateway
from ecommerce_agent.tools.query import QueryTools

ROOT = Path(__file__).resolve().parents[2]
PROMPT = PromptBundle(version="cache-v1", system="test")


def test_router_classifies_intents_model_tiers_and_cache_policy() -> None:
    router = DeterministicRouter()
    assert router.route("查詢最新 KPI").model_tier == "small"
    assert router.route("為什麼營收趨勢異常").intent == "diagnosis"
    assert router.route("規劃喚醒活動策略").intent == "strategy"
    action = router.route("請建立 issue 並執行任務")
    assert action.intent == "action" and action.cacheable is False
    report = router.route("產生每日晨報")
    assert report.intent == "report" and report.cacheable is False
    unknown = router.route("嗯")
    assert unknown.confidence < 0.5 and unknown.model_tier == "large"


def test_exact_semantic_and_context_isolation(tmp_path: Path) -> None:
    cache = DuckDBResponseCache(tmp_path / "cache.duckdb")
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    ops = identities.resolve("ops_01")
    cache.put(
        "收入趨勢 最近十天",
        "answer-v1",
        identity=ops,
        prompt_version="p1",
        data_version="d1",
    )
    assert cache.get(
        "收入趨勢 最近十天",
        identity=ops,
        prompt_version="p1",
        data_version="d1",
    ) == ("answer-v1", "exact")
    assert cache.get(
        "收入趨勢 最近十天資料",
        identity=ops,
        prompt_version="p1",
        data_version="d1",
    ) == ("answer-v1", "semantic")
    for identity, prompt, data in (
        (identities.resolve("pm_01"), "p1", "d1"),
        (ops, "p2", "d1"),
        (ops, "p1", "d2"),
    ):
        assert cache.get(
            "收入趨勢 最近十天",
            identity=identity,
            prompt_version=prompt,
            data_version=data,
        ) is None


def test_pii_is_never_semantic_cache_eligible(tmp_path: Path) -> None:
    cache = DuckDBResponseCache(tmp_path / "cache.duckdb")
    identity = DevIdentityProvider(ROOT / "configs/dev_users.yaml").resolve("support_01")
    cache.put(
        "查詢 U000001",
        "已處理 [REDACTED_USER_ID]",
        identity=identity,
        prompt_version="p1",
        data_version="d1",
    )
    assert cache.count() == 1 and cache.count(semantic_only=True) == 0
    assert cache.get(
        "查詢 U000001",
        identity=identity,
        prompt_version="p1",
        data_version="d1",
    )[1] == "exact"
    assert cache.get(
        "請查詢 U000001 資料",
        identity=identity,
        prompt_version="p1",
        data_version="d1",
    ) is None


def _agent_runtime(tmp_path: Path):
    traces = JsonlTraceStore(tmp_path / "traces.jsonl")
    tools = QueryTools(CsvMartRepository(ROOT / "data", ROOT / "data/schema.yml"))
    gateway = ToolGateway(tools, ROOT / "configs/rbac.yaml", traces)
    identities = DevIdentityProvider(ROOT / "configs/dev_users.yaml")
    cache = DuckDBResponseCache(tmp_path / "cache.duckdb")
    return gateway, identities, traces, cache


def test_agent_exact_cache_avoids_second_llm_call(tmp_path: Path) -> None:
    gateway, identities, traces, cache = _agent_runtime(tmp_path)
    client = FakeLLMClient([{"answer": "資料定義已查得。"}])
    agent = MinimalAgent(client, gateway, traces, PROMPT, response_cache=cache)
    identity = identities.resolve("ops_01")
    first = agent.run("查詢資料定義", identity=identity)
    second = agent.run("查詢資料定義", identity=identity)
    assert first.answer == second.answer
    assert any(event["event_type"] == "cache_hit" for event in traces.get(second.trace_id))


def test_action_requests_always_bypass_cache(tmp_path: Path) -> None:
    gateway, identities, traces, cache = _agent_runtime(tmp_path)
    client = FakeLLMClient([{"answer": "需要 dry-run。"}, {"answer": "仍需要 dry-run。"}])
    agent = MinimalAgent(client, gateway, traces, PROMPT, response_cache=cache)
    identity = identities.resolve("pm_01")
    first = agent.run("請建立 issue", identity=identity)
    second = agent.run("請建立 issue", identity=identity)
    assert first.answer != second.answer
    assert cache.count() == 0


def test_router_selects_distinct_small_and_large_clients(tmp_path: Path) -> None:
    gateway, identities, traces, _ = _agent_runtime(tmp_path)
    small = FakeLLMClient([{"answer": "small-client"}])
    large = FakeLLMClient([{"answer": "large-client"}])
    agent = MinimalAgent(
        small,
        gateway,
        traces,
        PROMPT,
        llm_clients={"small": small, "large": large},
    )
    identity = identities.resolve("ops_01")
    assert agent.run("查詢 KPI", identity=identity).answer == "small-client"
    assert agent.run("為什麼營收趨勢異常", identity=identity).answer == "large-client"
