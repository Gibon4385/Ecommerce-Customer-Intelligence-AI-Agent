from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest

from ecommerce_agent.auth.identity import DevIdentityProvider
from ecommerce_agent.rag.store import DuckDBRagStore, RagError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def rag(tmp_path: Path) -> tuple[DuckDBRagStore, DevIdentityProvider]:
    store = DuckDBRagStore(tmp_path / "knowledge.duckdb")
    store.rebuild_from_manifest(ROOT / "configs/rag_sources.yaml", root=ROOT)
    return store, DevIdentityProvider(ROOT / "configs/dev_users.yaml")


def test_rebuild_is_deterministic_and_preserves_metadata(rag) -> None:
    store, _ = rag
    first = store.rebuild_from_manifest(ROOT / "configs/rag_sources.yaml", root=ROOT)
    second = store.rebuild_from_manifest(ROOT / "configs/rag_sources.yaml", root=ROOT)
    assert first == second
    assert first["documents"] == 4 and first["chunks"] >= 10
    with duckdb.connect(str(store.path), read_only=True) as connection:
        row = connection.execute(
            "SELECT source_version, allowed_roles FROM rag_documents WHERE document_id = ?",
            ["customer-contact-policy"],
        ).fetchone()
    assert row == ("1.0", ["Support", "Marketing", "Admin"])


def test_retrieval_returns_locatable_citation_and_version(rag) -> None:
    store, identities = rag
    results = store.search(
        "同一客戶七天可以收到幾次行銷聯絡",
        identity=identities.resolve("support_01"),
    )
    assert results[0]["document_id"] == "customer-contact-policy"
    assert results[0]["source_version"] == "1.0"
    assert "knowledge_base/policies/customer_contact_policy.md#L" in results[0]["citation"]
    assert "七天內最多收到兩次" in results[0]["content"]


def test_role_filter_happens_before_similarity_ranking(rag) -> None:
    store, identities = rag
    support = store.search("緊急維護停用稽核紀錄", identity=identities.resolve("support_01"))
    assert support == []
    admin = store.search("緊急維護停用稽核紀錄", identity=identities.resolve("admin_01"))
    assert admin[0]["document_id"] == "admin-operations-policy"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("營收只計什麼訂單", "ops-mart-definitions"),
        ("為什麼 gross profit 是 NULL", "ops-mart-definitions"),
        ("漏斗有沒有 checkout event", "ops-mart-definitions"),
        ("task idempotency key 是什麼", "task-log-definitions"),
        ("任務誰可以看", "task-log-definitions"),
        ("客戶聯絡頻率", "customer-contact-policy"),
        ("hashed email 是否敏感", "customer-contact-policy"),
        ("對外聯絡如何核准", "customer-contact-policy"),
        ("runtime DuckDB 如何復原", "admin-operations-policy"),
        ("緊急維護可以停用稽核嗎", "admin-operations-policy"),
    ],
)
def test_known_answer_top_k_hit_rate(rag, query: str, expected: str) -> None:
    store, identities = rag
    results = store.search(query, identity=identities.resolve("admin_01"), top_k=3)
    assert expected in {item["document_id"] for item in results}


def test_no_evidence_and_input_validation(rag) -> None:
    store, identities = rag
    admin = identities.resolve("admin_01")
    assert store.search("量子火箭庫存政策", identity=admin) == []
    with pytest.raises(RagError, match="query"):
        store.search(" ", identity=admin)
    with pytest.raises(RagError, match="top_k"):
        store.search("policy", identity=admin, top_k=11)


def test_failed_rebuild_does_not_destroy_existing_index(rag, tmp_path: Path) -> None:
    store, identities = rag
    manifest = tmp_path / "rag_sources.yaml"
    shutil.copy(ROOT / "configs/rag_sources.yaml", manifest)
    text = manifest.read_text(encoding="utf-8").replace(
        "knowledge_base/data_dictionary/ops_marts.md", "missing.md"
    )
    manifest.write_text(text, encoding="utf-8")
    with pytest.raises(RagError, match="missing"):
        store.rebuild_from_manifest(manifest, root=ROOT)
    assert store.search("營收 completed", identity=identities.resolve("admin_01"))
