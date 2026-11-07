from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import yaml

from ecommerce_agent.auth.identity import Identity


class RagError(ValueError):
    pass


@dataclass(frozen=True)
class RagDocument:
    document_id: str
    path: Path
    version: str
    title: str
    allowed_roles: tuple[str, ...]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _terms(value: str) -> set[str]:
    normalized = value.casefold()
    latin = set(re.findall(r"[a-z0-9_]+", normalized))
    latin.update(part for term in tuple(latin) for part in term.split("_") if part)
    chinese_runs = re.findall(r"[\u3400-\u9fff]+", normalized)
    chinese = {
        run[index : index + 2]
        for run in chinese_runs
        for index in range(max(1, len(run) - 1))
    }
    return latin | chinese


class DuckDBRagStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.path))

    def migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_documents (
                    document_id VARCHAR PRIMARY KEY,
                    source_path VARCHAR NOT NULL,
                    source_version VARCHAR NOT NULL,
                    title VARCHAR NOT NULL,
                    allowed_roles VARCHAR[] NOT NULL,
                    content_hash VARCHAR NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    chunk_id VARCHAR PRIMARY KEY,
                    document_id VARCHAR NOT NULL,
                    heading VARCHAR NOT NULL,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL,
                    content VARCHAR NOT NULL,
                    term_json VARCHAR NOT NULL
                )
                """
            )

    def rebuild_from_manifest(self, manifest_path: Path, *, root: Path) -> dict[str, Any]:
        return self.rebuild_from_manifests([manifest_path], root=root)

    def rebuild_from_manifests(
        self, manifest_paths: list[Path], *, root: Path
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for manifest_path in manifest_paths:
            config = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            items.extend(config.get("documents", []))
        documents = [
            RagDocument(
                document_id=item["id"],
                path=root / item["path"],
                version=str(item["version"]),
                title=item["title"],
                allowed_roles=tuple(item["allowed_roles"]),
            )
            for item in items
        ]
        ids = [document.document_id for document in documents]
        if len(ids) != len(set(ids)):
            raise RagError("duplicate RAG document id across manifests")
        records: list[tuple[RagDocument, str, list[dict[str, Any]]]] = []
        for document in sorted(documents, key=lambda item: item.document_id):
            if not document.path.is_file():
                raise RagError(f"missing RAG source: {document.path}")
            content = document.path.read_text(encoding="utf-8")
            records.append((document, _hash(content), self._chunk(document, content)))
        with self._connect() as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.execute("DELETE FROM rag_chunks")
                connection.execute("DELETE FROM rag_documents")
                for document, content_hash, chunks in records:
                    connection.execute(
                        "INSERT INTO rag_documents VALUES (?, ?, ?, ?, ?, ?)",
                        [
                            document.document_id,
                            document.path.relative_to(root).as_posix(),
                            document.version,
                            document.title,
                            list(document.allowed_roles),
                            content_hash,
                        ],
                    )
                    for chunk in chunks:
                        connection.execute(
                            "INSERT INTO rag_chunks VALUES (?, ?, ?, ?, ?, ?, ?)",
                            [
                                chunk["chunk_id"],
                                document.document_id,
                                chunk["heading"],
                                chunk["line_start"],
                                chunk["line_end"],
                                chunk["content"],
                                json.dumps(sorted(_terms(chunk["content"]))),
                            ],
                        )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        fingerprint = "|".join(
            f"{document.document_id}:{document.version}:{content_hash}"
            for document, content_hash, _ in records
        )
        return {
            "index_version": _hash(fingerprint),
            "documents": len(records),
            "chunks": sum(len(chunks) for _, _, chunks in records),
        }

    def search(self, query: str, *, identity: Identity, top_k: int = 3) -> list[dict[str, Any]]:
        if not query.strip():
            raise RagError("query is required")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 10:
            raise RagError("top_k must be between 1 and 10")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT c.chunk_id, d.document_id, d.source_path, d.source_version,
                          d.title, c.heading, c.line_start, c.line_end, c.content, c.term_json
                   FROM rag_chunks c JOIN rag_documents d USING (document_id)
                   WHERE list_contains(d.allowed_roles, ?)
                   ORDER BY c.chunk_id""",
                [identity.role],
            ).fetchall()
        query_terms = _terms(query)
        scored = []
        for row in rows:
            terms = set(json.loads(row[9]))
            overlap = query_terms & terms
            if not overlap:
                continue
            score = len(overlap) / max(len(query_terms), 1)
            scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], item[1][0]))
        return [
            {
                "chunk_id": row[0],
                "document_id": row[1],
                "source_version": row[3],
                "title": row[4],
                "heading": row[5],
                "content": row[8],
                "score": round(score, 6),
                "citation": f"{row[2]}#L{row[6]}-L{row[7]}",
            }
            for score, row in scored[:top_k]
        ]

    def _chunk(self, document: RagDocument, content: str) -> list[dict[str, Any]]:
        lines = content.splitlines()
        chunks: list[dict[str, Any]] = []
        heading = document.title
        body: list[tuple[int, str]] = []

        def flush() -> None:
            if not body:
                return
            text = "\n".join(line for _, line in body).strip()
            if text:
                start, end = body[0][0], body[-1][0]
                chunks.append(
                    {
                        "chunk_id": _hash(
                            f"{document.document_id}:{document.version}:{heading}:{start}:{text}"
                        )[:24],
                        "heading": heading,
                        "line_start": start,
                        "line_end": end,
                        "content": text,
                    }
                )
            body.clear()

        for line_number, line in enumerate(lines, start=1):
            if match := re.match(r"^#{1,6}\s+(.+?)\s*$", line):
                flush()
                heading = match.group(1)
            elif line.strip():
                body.append((line_number, line))
        flush()
        return chunks
