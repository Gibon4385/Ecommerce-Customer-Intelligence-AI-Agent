# HTML templates stay inline and intentionally contain long literal fragments.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ecommerce_agent.auth.identity import Identity
from ecommerce_agent.knowledge import KnowledgeStudio, KnowledgeStudioError
from ecommerce_agent.knowledge.studio import TEMPLATE_FIELDS
from ecommerce_agent.monitoring import DISPLAY_TIMEZONE, _local_parts, aggregate_interactions
from ecommerce_agent.observability.tracing import JsonlTraceStore


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
body {{ font-family: system-ui,sans-serif; margin:0; background:#f5f7f9; color:#17212b; }}
nav {{ background:#17324d; padding:16px; }} nav a {{ color:white; margin-right:18px; }}
main {{ max-width:1100px; margin:auto; padding:24px; }} section {{ background:white; padding:20px;
margin:16px 0; border:1px solid #dbe2e8; border-radius:10px; }} label {{ display:block; margin:10px 0; }}
input,textarea,select {{ width:100%; box-sizing:border-box; padding:8px; }} textarea {{ min-height:90px; }}
button {{ padding:9px 14px; }} table {{ border-collapse:collapse; width:100%; }} th,td {{ padding:7px;
border-bottom:1px solid #ddd; text-align:left; vertical-align:top; }} code {{ white-space:pre-wrap; }}
details {{ margin:6px 0; }} pre {{ white-space:pre-wrap; word-break:break-word; max-height:28rem; overflow:auto; }}
.status {{ font-weight:700; }} .muted {{ color:#5d6b78; }}
</style></head><body><nav><a href="/">Home</a><a href="/knowledge">Knowledge</a>
<a href="/monitoring">Monitoring</a></nav><main><h1>{html.escape(title)}</h1>{body}</main></body></html>"""


class PortalApp:
    def __init__(
        self,
        *,
        root: Path,
        identity: Identity,
        traces: JsonlTraceStore,
        csrf_token: str | None = None,
    ):
        self.root = root
        self.identity = identity
        self.traces = traces
        self.knowledge = KnowledgeStudio(root, traces)
        self.csrf_token = csrf_token or secrets.token_urlsafe(24)

    def home(self) -> str:
        body = (
            f"<section><h2>固定身分</h2><p>{html.escape(self.identity.user_id)} · "
            f"{html.escape(self.identity.role)} · {html.escape(self.identity.data_scope)}</p></section>"
            "<section><h2>Operations Snapshot</h2><p>使用 ecommerce-agent-dashboard 產生固定快照。</p></section>"
            "<section><h2>Knowledge Center</h2><p>建立受治理的業務知識草稿。</p></section>"
            "<section><h2>Monitoring</h2><p>僅 Admin 可查看遮罩後 interaction timeline。</p></section>"
        )
        return _page("Local Demo Portal", body)

    def knowledge_page(self, message: str = "") -> str:
        published_rows = "".join(
            "<tr>"
            f"<td>{html.escape(item['title'])}</td><td>{html.escape(item['template_type'].replace('_', ' ').title())}</td>"
            f"<td>{html.escape(item['domain'])}</td><td>{html.escape(item['version'])}</td>"
            f"<td>{html.escape(', '.join(item['allowed_roles']))}</td><td>{html.escape(item['management'])}</td>"
            f"<td>{html.escape(item['updated'])}</td><td>{self._published_actions(item)}</td></tr>"
            for item in self.knowledge.list_published(identity=self.identity)
        )
        draft_rows = "".join(
            "<tr>"
            f"<td>{html.escape(item['title'])}</td><td>{html.escape(item['template_type'])}</td>"
            f"<td>{html.escape(item['status'])}</td><td>{item['version']}</td>"
            f"<td>{self._actions(item)}</td></tr>"
            for item in self.knowledge.list_drafts(identity=self.identity)
        )
        forms = "" if self.identity.role not in {"PM", "Marketing", "Ops", "Admin"} else self._forms()
        notice = f"<p>{html.escape(message)}</p>" if message else ""
        return _page(
            "Business Knowledge Center",
            notice
            + "<section><h2>Published Knowledge</h2><table><tr><th>Title</th><th>Type</th><th>Domain</th>"
            "<th>Version</th><th>Audience</th><th>Management</th><th>Updated</th><th>Action</th>"
            f"</tr>{published_rows}</table></section>"
            + "<section><h2>Drafts and Reviews</h2><table><tr><th>標題</th><th>類型</th><th>狀態</th>"
            f"<th>版本</th><th>動作</th></tr>{draft_rows}</table></section>"
            f"<section><h2>Add Knowledge</h2><p>使用下列固定模板建立新知識。</p></section>{forms}",
        )

    def published_page(self, document_id: str) -> str:
        item = self.knowledge.get_published(document_id, identity=self.identity)
        sections = "".join(
            f"<section><h2>{html.escape(section['heading'])}</h2>"
            f"<p>{html.escape(section['content'])}</p></section>"
            for section in item["sections"]
        )
        metadata = (
            f"<p>Version {html.escape(item['version'])} · {html.escape(item['management'])} · "
            f"Audience: {html.escape(', '.join(item['allowed_roles']))}</p>"
        )
        return _page(str(item["title"]), metadata + sections)

    def monitoring_page(self) -> str:
        if self.identity.role != "Admin":
            raise PermissionError("Monitoring requires Admin")
        trace_id = self.traces.new_trace_id()
        self.traces.record(
            "monitoring_access",
            trace_id,
            role=self.identity.role,
            channel=self.identity.channel,
            action="view_recent",
        )
        rows = "".join(self._monitoring_row(item) for item in aggregate_interactions(self.traces.recent(100)))
        return _page(
            "Interaction Monitoring",
            f"<section><p>顯示時區：<strong>{DISPLAY_TIMEZONE}</strong>（原始事件保存 UTC）</p>"
            "<table><tr><th>Date</th><th>Time</th><th>Timezone</th><th>Status</th><th>Channel</th>"
            "<th>Role</th><th>Request</th><th>Result</th><th>Duration</th><th>Trace</th>"
            f"</tr>{rows}</table></section>",
        )

    def create(self, form: dict[str, list[str]]) -> str:
        self._check_csrf(form)
        template = self._one(form, "template_type")
        content = {key: self._one(form, key) for key in TEMPLATE_FIELDS.get(template, ())}
        trace_id = self.traces.new_trace_id()
        draft = self.knowledge.create_draft(
            template_type=template,
            title=self._one(form, "title"),
            domain=self._one(form, "domain"),
            owner=self._one(form, "owner"),
            allowed_roles=form.get("allowed_roles", []),
            content=content,
            identity=self.identity,
            trace_id=trace_id,
        )
        return self.knowledge_page(f"已建立草稿 {draft['draft_id']}")

    def transition(self, draft_id: str, action: str, form: dict[str, list[str]]) -> str:
        self._check_csrf(form)
        trace_id = self.traces.new_trace_id()
        if action == "submit":
            self.knowledge.submit(draft_id, identity=self.identity, trace_id=trace_id)
        elif action == "publish":
            self.knowledge.publish(draft_id, identity=self.identity, trace_id=trace_id)
        else:
            raise KnowledgeStudioError("unsupported transition")
        return self.knowledge_page(f"已完成 {action}")

    def create_version(self, document_id: str, form: dict[str, list[str]]) -> str:
        self._check_csrf(form)
        draft = self.knowledge.create_new_version(
            document_id, identity=self.identity, trace_id=self.traces.new_trace_id()
        )
        return self.knowledge_page(f"已從目前發布版本建立草稿 {draft['draft_id']}")

    def _published_actions(self, item: dict[str, object]) -> str:
        view = f'<a href="/knowledge/published/{html.escape(str(item["document_id"]))}">View</a>'
        if item["management_mode"] != "business_managed" or self.identity.role not in {"PM", "Marketing", "Ops", "Admin"}:
            return view
        return view + (
            f'<form method="post" action="/knowledge/published/{html.escape(str(item["document_id"]))}/new-version">'
            f'<input type="hidden" name="csrf" value="{html.escape(self.csrf_token)}">'
            "<button>Create new version</button></form>"
        )

    @staticmethod
    def _monitoring_row(item: dict[str, object]) -> str:
        timeline = []
        events = item["events"]
        if not isinstance(events, list):
            raise TypeError("monitoring events must be a list")
        for event in events:
            if not isinstance(event, dict):
                raise TypeError("monitoring event must be an object")
            date, time = _local_parts(str(event["timestamp"]))
            payload = json.dumps(event["payload"], ensure_ascii=False, indent=2, sort_keys=True)
            timeline.append(
                f"<li><strong>{date} {time}</strong> · {html.escape(str(event['event_type']).replace('_', ' ').title())}"
                "<details><summary>Redacted payload</summary>"
                f"<pre>{html.escape(payload)}</pre></details></li>"
            )
        trace_id = str(item["trace_id"])
        details = f'<details><summary>{html.escape(trace_id[:8])}</summary><p>{html.escape(trace_id)}</p><ol>{"".join(timeline)}</ol></details>'
        return (
            "<tr>"
            f"<td>{item['date']}</td><td>{item['time']}</td><td>{item['timezone']}</td>"
            f"<td class=\"status\">{html.escape(str(item['status']))}</td>"
            f"<td>{html.escape(str(item['channel']))}</td><td>{html.escape(str(item['role']))}</td>"
            f"<td>{html.escape(str(item['request']))}</td><td>{html.escape(str(item['result']))}</td>"
            f"<td>{html.escape(str(item['duration']))}</td><td>{details}</td></tr>"
        )

    def _actions(self, item: dict[str, object]) -> str:
        actions = []
        if item["status"] == "draft":
            actions.append(self._action_form(str(item["draft_id"]), "submit", "送審"))
        if item["status"] == "in_review" and self.identity.role == "Admin":
            actions.append(self._action_form(str(item["draft_id"]), "publish", "發布"))
        return "".join(actions)

    def _action_form(self, draft_id: str, action: str, label: str) -> str:
        return (
            f'<form method="post" action="/knowledge/{html.escape(draft_id)}/{action}">'
            f'<input type="hidden" name="csrf" value="{html.escape(self.csrf_token)}">'
            f"<button>{html.escape(label)}</button></form>"
        )

    def _forms(self) -> str:
        blocks = []
        for template, fields in TEMPLATE_FIELDS.items():
            field_html = "".join(
                f'<label>{html.escape(field.replace("_", " ").title())}'
                f'<textarea name="{html.escape(field)}" required></textarea></label>'
                for field in fields
            )
            role_options = "".join(
                f'<option value="{role}">{role}</option>'
                for role in ("Support", "PM", "Marketing", "Ops", "Admin")
            )
            blocks.append(
                f'<section><h2>新增 {html.escape(template)}</h2><form method="post" action="/knowledge/create">'
                f'<input type="hidden" name="csrf" value="{html.escape(self.csrf_token)}">'
                f'<input type="hidden" name="template_type" value="{html.escape(template)}">'
                '<label>Title<input name="title" required></label><label>Domain<input name="domain" required></label>'
                '<label>Owner<input name="owner" required></label>'
                f'<label>Allowed roles<select name="allowed_roles" multiple required>{role_options}</select></label>'
                f"{field_html}<button>建立草稿</button></form></section>"
            )
        return "".join(blocks)

    def _check_csrf(self, form: dict[str, list[str]]) -> None:
        if self._one(form, "csrf") != self.csrf_token:
            raise PermissionError("invalid CSRF token")

    @staticmethod
    def _one(form: dict[str, list[str]], key: str) -> str:
        values = form.get(key, [])
        if len(values) != 1:
            raise KnowledgeStudioError(f"{key} is required exactly once")
        return values[0]


def _handler(app: PortalApp):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                if path == "/":
                    self._send(app.home())
                elif path == "/knowledge":
                    self._send(app.knowledge_page())
                elif match := re.fullmatch(r"/knowledge/published/([^/]+)", path):
                    self._send(app.published_page(match.group(1)))
                elif path == "/monitoring":
                    self._send(app.monitoring_page())
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except PermissionError as exc:
                self.send_error(HTTPStatus.FORBIDDEN, str(exc))

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            path = urlparse(self.path).path
            try:
                if path == "/knowledge/create":
                    self._send(app.create(form))
                    return
                version_match = re.fullmatch(r"/knowledge/published/([^/]+)/new-version", path)
                if version_match:
                    self._send(app.create_version(version_match.group(1), form))
                    return
                match = re.fullmatch(r"/knowledge/([^/]+)/(submit|publish)", path)
                if match:
                    self._send(app.transition(match.group(1), match.group(2), form))
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except (KnowledgeStudioError, PermissionError) as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def _send(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    import re

    return Handler


def main(argv: list[str] | None = None) -> int:
    from ecommerce_agent.cli import ROOT, build_runtime

    parser = argparse.ArgumentParser(prog="ecommerce-agent-portal")
    parser.add_argument("--as", dest="user_id", required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    identities, _, traces = build_runtime()
    identity = identities.resolve(args.user_id, channel="portal")
    app = PortalApp(root=ROOT, identity=identity, traces=traces)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _handler(app))
    print(f"Portal: http://127.0.0.1:{args.port} ({identity.user_id}/{identity.role})")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
