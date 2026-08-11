"""Authenticated standard-library HTTP API over existing application services."""

from __future__ import annotations

import hmac
import json
from collections.abc import Iterable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .constants import PERMISSIONS
from .database import KnowledgeDB
from .jobs import JobQueue
from .retrieval import HybridRetriever
from .schema_runtime import require_schema

MAX_REQUEST_BYTES = 1024 * 1024


def create_api_server(
    workspace: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
    tenant_id: str = "local",
    principal_id: str = "local-user",
    allowed_access: Iterable[str] = ("public",),
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1", "localhost"} and not token:
        raise ValueError("non-loopback API binding requires ONE_SKILLS_API_TOKEN")
    if not tenant_id or not principal_id:
        raise ValueError("API tenant and principal must be non-empty")
    access_scope = frozenset(allowed_access)
    if not access_scope or not access_scope <= set(PERMISSIONS):
        raise ValueError("API allowed access levels are invalid")
    database_path = workspace.resolve() / ".one" / "knowledge.db"
    with KnowledgeDB(database_path) as database:
        identity = database.connection.execute(
            "SELECT p.id FROM principals p "
            "JOIN tenants t ON t.id = p.tenant_id "
            "WHERE p.tenant_id = ? AND p.id = ?",
            (tenant_id, principal_id),
        ).fetchone()
        if not identity:
            raise ValueError(
                f"API principal does not exist: {tenant_id}/{principal_id}"
            )

    class Handler(BaseHTTPRequestHandler):
        server_version = "one-skills/0.1"

        def _json(self, status: HTTPStatus, value: object) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if not token:
                return True
            header = self.headers.get("Authorization", "")
            expected = f"Bearer {token}"
            return hmac.compare_digest(header, expected)

        def _require_auth(self) -> bool:
            if self._authorized():
                return True
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return False

        def _body(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("request body must be between 1 byte and 1 MiB")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Content-Type must be application/json")
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("request JSON must be an object")
            return value

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._json(HTTPStatus.OK, {"status": "ok"})
                return
            if not self._require_auth():
                return
            try:
                if parsed.path == "/v1/search":
                    query = parse_qs(parsed.query)
                    text = query.get("q", [""])[0].strip()
                    if not text:
                        raise ValueError("q is required")
                    with KnowledgeDB(database_path) as database:
                        results = HybridRetriever(
                            database,
                            tenant_id,
                            principal_id,
                        ).search(
                            text,
                            set(access_scope),
                            10,
                        )
                    self._json(
                        HTTPStatus.OK,
                        {
                            "results": [
                                {
                                    "id": item["id"],
                                    "score": item["score"],
                                    "text": item["text"],
                                    "locator": item["source_locator"],
                                }
                                for item in results
                            ]
                        },
                    )
                    return
                if parsed.path.startswith("/v1/jobs/"):
                    job_id = parsed.path.removeprefix("/v1/jobs/")
                    with KnowledgeDB(database_path) as database:
                        result = JobQueue(database).get(job_id)
                    self._json(HTTPStatus.OK, result)
                    return
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def do_POST(self) -> None:
            if not self._require_auth():
                return
            try:
                if urlparse(self.path).path != "/v1/jobs":
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                body = self._body()
                require_schema(
                    body,
                    "job-request.schema.json",
                    "HTTP job request",
                )
                unknown = set(body) - {
                    "type",
                    "payload",
                    "max_attempts",
                }
                if unknown:
                    raise ValueError(
                        "job request has unsupported fields: "
                        + ", ".join(sorted(unknown))
                    )
                with KnowledgeDB(database_path) as database:
                    job_id = JobQueue(database).enqueue(
                        body["type"],
                        body["payload"],
                        body.get("max_attempts", 3),
                        actor_id="api",
                    )
                self._json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})
            except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return ThreadingHTTPServer((host, port), Handler)
