from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml

from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.guardrails import InputGuardrail, InputGuardrailError
from ecommerce_agent.observability.tracing import JsonlTraceStore, redact_text
from ecommerce_agent.rag.store import DuckDBRagStore


class KnowledgeStudioError(ValueError):
    pass


TEMPLATE_FIELDS = {
    "metric_definition": ("business_definition", "grain", "null_policy"),
    "business_policy": ("scenario", "rule", "exception", "when_exceeded"),
    "answer_playbook": ("scenario", "answer_steps", "forbidden_claims"),
}
VALID_ROLES = {"Support", "PM", "Marketing", "Ops", "Admin"}
EDITOR_ROLES = {"PM", "Marketing", "Ops", "Admin"}
MANAGEMENT_MODES = {"business_managed", "system_managed", "locked"}
SAFE_SOURCE_PREFIXES = (
    "knowledge_base/data_dictionary/",
    "knowledge_base/policies/",
    "runtime/knowledge_studio/published/",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        slug = "knowledge-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return slug[:64]


class KnowledgeStudio:
    def __init__(self, root: Path, traces: JsonlTraceStore):
        self.root = root
        self.traces = traces
        self.runtime = root / "runtime/knowledge_studio"
        self.database = self.runtime / "drafts.duckdb"
        self.published = self.runtime / "published"
        self.manifest = self.runtime / "rag_sources.yaml"
        self.runtime.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.database)) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_drafts (
                    draft_id VARCHAR PRIMARY KEY,
                    document_id VARCHAR NOT NULL,
                    template_type VARCHAR NOT NULL,
                    title VARCHAR NOT NULL,
                    domain VARCHAR NOT NULL,
                    owner VARCHAR NOT NULL,
                    allowed_roles VARCHAR[] NOT NULL,
                    content_json VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    version INTEGER NOT NULL,
                    created_by VARCHAR NOT NULL,
                    reviewed_by VARCHAR,
                    created_at VARCHAR NOT NULL,
                    updated_at VARCHAR NOT NULL
                )"""
            )

    def create_draft(
        self,
        *,
        template_type: str,
        title: str,
        domain: str,
        owner: str,
        allowed_roles: list[str],
        content: dict[str, Any],
        identity: Identity,
        trace_id: str,
        document_id: str | None = None,
        base_version: int = 0,
    ) -> dict[str, Any]:
        if identity.role not in EDITOR_ROLES:
            raise KnowledgeStudioError("role cannot edit business knowledge")
        self._validate(template_type, title, domain, owner, allowed_roles, content)
        preserves_published_scope = False
        if document_id is not None:
            try:
                source = self._repository_manifest_entry(document_id)
                preserves_published_scope = (
                    source.get("management_mode") == "business_managed"
                    and list(source.get("allowed_roles", [])) == allowed_roles
                    and identity.role in allowed_roles
                )
            except (KnowledgeStudioError, OSError, yaml.YAMLError):
                preserves_published_scope = False
        if (
            identity.role != "Admin"
            and not preserves_published_scope
            and not set(allowed_roles) <= {identity.role, "Admin"}
        ):
            raise KnowledgeStudioError("editor cannot grant knowledge to another business role")
        draft_id = str(uuid.uuid4())
        document_id = document_id or _slug(title)
        timestamp = _now()
        with duckdb.connect(str(self.database)) as connection:
            current_row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM knowledge_drafts WHERE document_id=?",
                [document_id],
            ).fetchone()
            assert current_row is not None
            current = current_row[0]
            version = max(int(current), base_version) + 1
            connection.execute(
                "INSERT INTO knowledge_drafts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    draft_id,
                    document_id,
                    template_type,
                    title,
                    domain,
                    owner,
                    allowed_roles,
                    json.dumps(content, ensure_ascii=False, sort_keys=True),
                    "draft",
                    version,
                    identity.user_id,
                    None,
                    timestamp,
                    timestamp,
                ],
            )
        self.traces.record(
            "knowledge_draft_created",
            trace_id,
            draft_id=draft_id,
            document_id=document_id,
            template_type=template_type,
        )
        return self.get(draft_id)

    def list_published(self, *, identity: Identity) -> list[dict[str, Any]]:
        """Return only explicitly governed, role-authorized repository knowledge."""
        documents: list[dict[str, Any]] = []
        for raw in self._governed_manifest_entries():
            roles = raw.get("allowed_roles", [])
            mode = raw.get("management_mode")
            template = raw.get("template_type")
            source = str(raw.get("path", ""))
            if identity.role not in roles or mode not in MANAGEMENT_MODES:
                continue
            if not source.startswith(SAFE_SOURCE_PREFIXES) or ".." in Path(source).parts:
                continue
            if mode == "business_managed" and template not in TEMPLATE_FIELDS:
                continue
            if mode != "business_managed" and template != "managed_reference":
                continue
            documents.append(
                {
                    "document_id": str(raw["id"]),
                    "title": str(raw["title"]),
                    "template_type": str(template),
                    "domain": str(raw["domain"]),
                    "version": str(raw["version"]),
                    "allowed_roles": list(roles),
                    "management_mode": str(mode),
                    "management": {
                        "business_managed": "Editable",
                        "system_managed": "Read only",
                        "locked": "Locked",
                    }[mode],
                    "updated": raw.get("updated") or "Unknown",
                }
            )
        return documents

    def get_published(self, document_id: str, *, identity: Identity) -> dict[str, Any]:
        matches = [
            item for item in self.list_published(identity=identity)
            if item["document_id"] == document_id
        ]
        if not matches:
            raise KnowledgeStudioError("published document not found")
        item = matches[0]
        raw = self._repository_manifest_entry(document_id)
        source = self.root / str(raw["path"])
        item["sections"] = self._markdown_sections(source.read_text(encoding="utf-8"))
        return item

    def create_new_version(
        self, document_id: str, *, identity: Identity, trace_id: str
    ) -> dict[str, Any]:
        published = self.get_published(document_id, identity=identity)
        if published["management_mode"] != "business_managed":
            raise KnowledgeStudioError("published document is not editable")
        raw = self._repository_manifest_entry(document_id)
        content = raw.get("template_content")
        if not isinstance(content, dict):
            raise KnowledgeStudioError("published document has no governed template content")
        try:
            base_version = int(str(published["version"]).split(".")[0])
        except ValueError as exc:
            raise KnowledgeStudioError("published version is not supported") from exc
        return self.create_draft(
            template_type=str(published["template_type"]),
            title=str(published["title"]),
            domain=str(published["domain"]),
            owner=str(published["domain"]),
            allowed_roles=list(published["allowed_roles"]),
            content={str(key): value for key, value in content.items()},
            identity=identity,
            trace_id=trace_id,
            document_id=document_id,
            base_version=base_version,
        )

    def submit(self, draft_id: str, *, identity: Identity, trace_id: str) -> dict[str, Any]:
        draft = self.get(draft_id)
        if identity.user_id != draft["created_by"] and identity.role != "Admin":
            raise KnowledgeStudioError("only creator or Admin can submit")
        return self._transition(draft_id, "draft", "in_review", identity, trace_id)

    def publish(self, draft_id: str, *, identity: Identity, trace_id: str) -> dict[str, Any]:
        if identity.role != "Admin":
            raise KnowledgeStudioError("Admin review is required to publish")
        draft = self.get(draft_id)
        if draft["status"] != "in_review":
            raise KnowledgeStudioError("draft must be in_review before publish")
        markdown = self.render(draft)
        relative_path = Path("runtime/knowledge_studio/published") / (
            f"{draft['document_id']}-v{draft['version']}.md"
        )
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
        entry = {
            "id": draft["document_id"],
            "path": relative_path.as_posix(),
            "version": str(draft["version"]),
            "title": draft["title"],
            "allowed_roles": draft["allowed_roles"],
            "management_mode": "business_managed",
            "template_type": draft["template_type"],
            "domain": draft["domain"],
            "updated": _now(),
            "template_content": draft["content"],
        }
        self._validate_candidate(entry)
        manifest = self._manifest_data()
        manifest["documents"] = [
            item for item in manifest["documents"] if item["id"] != draft["document_id"]
        ] + [entry]
        temporary = self.manifest.with_suffix(".yaml.tmp")
        temporary.write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        temporary.replace(self.manifest)
        with duckdb.connect(str(self.database)) as connection:
            connection.execute(
                """UPDATE knowledge_drafts
                   SET status='published', reviewed_by=?, updated_at=?
                   WHERE draft_id=?""",
                [identity.user_id, _now(), draft_id],
            )
        self.traces.record(
            "knowledge_published",
            trace_id,
            draft_id=draft_id,
            document_id=draft["document_id"],
            content_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        )
        return self.get(draft_id)

    def archive(self, document_id: str, *, identity: Identity, trace_id: str) -> None:
        if identity.role != "Admin":
            raise KnowledgeStudioError("Admin is required to archive")
        manifest = self._manifest_data()
        before = len(manifest["documents"])
        manifest["documents"] = [
            item for item in manifest["documents"] if item["id"] != document_id
        ]
        if len(manifest["documents"]) == before:
            raise KnowledgeStudioError("published document not found")
        temporary = self.manifest.with_suffix(".yaml.tmp")
        temporary.write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        temporary.replace(self.manifest)
        self.traces.record("knowledge_archived", trace_id, document_id=document_id)

    def get(self, draft_id: str) -> dict[str, Any]:
        with duckdb.connect(str(self.database), read_only=True) as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_drafts WHERE draft_id=?", [draft_id]
            ).fetchone()
            columns = [item[0] for item in connection.description]
        if row is None:
            raise KnowledgeStudioError("draft not found")
        result = dict(zip(columns, row, strict=True))
        result["content"] = json.loads(result.pop("content_json"))
        return result

    def list_drafts(self, *, identity: Identity) -> list[dict[str, Any]]:
        with duckdb.connect(str(self.database), read_only=True) as connection:
            if identity.role == "Admin":
                rows = connection.execute(
                    "SELECT draft_id FROM knowledge_drafts ORDER BY updated_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT draft_id FROM knowledge_drafts
                       WHERE created_by=? AND list_contains(allowed_roles, ?)
                       ORDER BY updated_at DESC""",
                    [identity.user_id, identity.role],
                ).fetchall()
            ids = [row[0] for row in rows]
        return [self.get(draft_id) for draft_id in ids]

    def render(self, draft: dict[str, Any]) -> str:
        content = draft["content"]
        lines = [f"# {draft['title']}", "", f"Domain: {draft['domain']}", ""]
        for key in TEMPLATE_FIELDS[draft["template_type"]]:
            label = key.replace("_", " ").title()
            value = content[key]
            lines.extend([f"## {label}", "", str(value), ""])
        return "\n".join(lines).rstrip() + "\n"

    def _validate(
        self,
        template_type: str,
        title: str,
        domain: str,
        owner: str,
        allowed_roles: list[str],
        content: dict[str, Any],
    ) -> None:
        if template_type not in TEMPLATE_FIELDS:
            raise KnowledgeStudioError("unsupported knowledge template")
        if not all(isinstance(value, str) and value.strip() for value in (title, domain, owner)):
            raise KnowledgeStudioError("title, domain and owner are required")
        if not allowed_roles or not set(allowed_roles) <= VALID_ROLES:
            raise KnowledgeStudioError("allowed_roles contains an invalid role")
        required = set(TEMPLATE_FIELDS[template_type])
        if set(content) != required or not all(str(content[key]).strip() for key in required):
            raise KnowledgeStudioError("template content does not match required fields")
        combined = "\n".join(
            [title, domain, owner, *(str(content[key]) for key in sorted(content))]
        )
        if redact_text(combined) != combined:
            raise KnowledgeStudioError("knowledge contains PII, restricted identifiers or secrets")
        try:
            InputGuardrail().validate(combined)
        except InputGuardrailError as exc:
            raise KnowledgeStudioError(f"knowledge blocked by {exc.category}") from exc
        if re.search(r"(?i)(call|invoke|execute|呼叫|執行).{0,20}(tool|工具|sql|shell)", combined):
            raise KnowledgeStudioError("knowledge cannot instruct executable tool or command use")

    def _transition(
        self,
        draft_id: str,
        expected: str,
        target: str,
        identity: Identity,
        trace_id: str,
    ) -> dict[str, Any]:
        draft = self.get(draft_id)
        if draft["status"] != expected:
            raise KnowledgeStudioError(f"expected {expected} status")
        with duckdb.connect(str(self.database)) as connection:
            connection.execute(
                "UPDATE knowledge_drafts SET status=?, updated_at=? WHERE draft_id=?",
                [target, _now(), draft_id],
            )
        self.traces.record(
            "knowledge_status_changed", trace_id, draft_id=draft_id, status=target
        )
        return self.get(draft_id)

    def _manifest_data(self) -> dict[str, Any]:
        if not self.manifest.is_file():
            return {"documents": []}
        return yaml.safe_load(self.manifest.read_text(encoding="utf-8")) or {"documents": []}

    def _repository_manifest_entry(self, document_id: str) -> dict[str, Any]:
        for item in self._governed_manifest_entries():
            if item.get("id") == document_id:
                return item
        raise KnowledgeStudioError("published document not found")

    def _governed_manifest_entries(self) -> list[dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        for path in (self.root / "configs/rag_sources.yaml", self.manifest):
            if not path.is_file():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for item in data.get("documents", []):
                if isinstance(item, dict) and item.get("id"):
                    # Runtime is current and is intentionally loaded after repository defaults.
                    entries[str(item["id"])] = item
        return list(entries.values())

    @staticmethod
    def _markdown_sections(markdown: str) -> list[dict[str, str]]:
        sections: list[dict[str, str]] = []
        heading = "Overview"
        lines: list[str] = []
        for line in markdown.splitlines():
            if line.startswith("# "):
                continue
            if line.startswith("## "):
                if any(item.strip() for item in lines):
                    sections.append({"heading": heading, "content": "\n".join(lines).strip()})
                heading, lines = line[3:].strip(), []
            else:
                lines.append(line)
        if any(item.strip() for item in lines):
            sections.append({"heading": heading, "content": "\n".join(lines).strip()})
        return sections

    def _validate_candidate(self, entry: dict[str, Any]) -> None:
        candidate_manifest = self.runtime / "candidate_manifest.yaml"
        candidate_manifest.write_text(
            yaml.safe_dump({"documents": [entry]}, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        candidate = DuckDBRagStore(self.runtime / "candidate.duckdb")
        candidate.rebuild_from_manifests(
            [self.root / "configs/rag_sources.yaml", candidate_manifest], root=self.root
        )
