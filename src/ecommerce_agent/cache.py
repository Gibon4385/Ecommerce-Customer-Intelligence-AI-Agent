from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import duckdb

from ecommerce_agent.auth.identity import Identity


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _terms(value: str) -> set[str]:
    normalized = _normalize(value)
    latin = set(re.findall(r"[a-z0-9_]+", normalized))
    runs = re.findall(r"[\u3400-\u9fff]+", normalized)
    chinese = {run[i : i + 2] for run in runs for i in range(max(1, len(run) - 1))}
    return latin | chinese


def contains_sensitive(value: str) -> bool:
    patterns = (
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        r"(?<!\w)(?:\+?\d[\d -]{7,}\d)(?!\w)",
        r"\bU\d{6}\b",
        r"\b[a-fA-F0-9]{64}\b",
        r"(?:姓名|customer[_ ]?name|name)\s*[:：]",
    )
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


class DuckDBResponseCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(path)) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS response_cache (
                    cache_key VARCHAR PRIMARY KEY,
                    question VARCHAR NOT NULL,
                    term_json VARCHAR NOT NULL,
                    answer VARCHAR NOT NULL,
                    role VARCHAR NOT NULL,
                    data_scope VARCHAR NOT NULL,
                    prompt_version VARCHAR NOT NULL,
                    data_version VARCHAR NOT NULL,
                    semantic_eligible BOOLEAN NOT NULL
                )"""
            )

    def get(
        self,
        question: str,
        *,
        identity: Identity,
        prompt_version: str,
        data_version: str,
        allow_semantic: bool = True,
    ) -> tuple[str, str] | None:
        key = self._key(question, identity, prompt_version, data_version)
        with duckdb.connect(str(self.path)) as connection:
            exact = connection.execute(
                "SELECT answer FROM response_cache WHERE cache_key=?", [key]
            ).fetchone()
            if exact:
                return exact[0], "exact"
            if not allow_semantic or contains_sensitive(question):
                return None
            rows = connection.execute(
                """SELECT question, term_json, answer FROM response_cache
                WHERE role=? AND data_scope=? AND prompt_version=? AND data_version=?
                  AND semantic_eligible=true""",
                [identity.role, identity.data_scope, prompt_version, data_version],
            ).fetchall()
        requested = _terms(question)
        best: tuple[float, str] | None = None
        for _, term_json, answer in rows:
            cached = set(json.loads(term_json))
            score = len(requested & cached) / max(len(requested | cached), 1)
            if score >= 0.6 and (best is None or score > best[0]):
                best = (score, answer)
        return (best[1], "semantic") if best else None

    def put(
        self,
        question: str,
        answer: str,
        *,
        identity: Identity,
        prompt_version: str,
        data_version: str,
        semantic_eligible: bool = True,
    ) -> None:
        eligible = semantic_eligible and not contains_sensitive(question + " " + answer)
        key = self._key(question, identity, prompt_version, data_version)
        with duckdb.connect(str(self.path)) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO response_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    key,
                    question,
                    json.dumps(sorted(_terms(question))),
                    answer,
                    identity.role,
                    identity.data_scope,
                    prompt_version,
                    data_version,
                    eligible,
                ],
            )

    def count(self, *, semantic_only: bool = False) -> int:
        condition = " WHERE semantic_eligible=true" if semantic_only else ""
        with duckdb.connect(str(self.path), read_only=True) as connection:
            row = connection.execute(
                f"SELECT COUNT(*) FROM response_cache{condition}"
            ).fetchone()
        assert row is not None
        return row[0]

    @staticmethod
    def _key(
        question: str, identity: Identity, prompt_version: str, data_version: str
    ) -> str:
        value = "|".join(
            (
                _normalize(question),
                identity.role,
                identity.data_scope,
                prompt_version,
                data_version,
            )
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
