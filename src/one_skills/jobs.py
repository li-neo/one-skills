"""Persistent leased job queue and append-only audit events."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread
from typing import Any
from urllib.parse import urlparse

from .benchmark import run_profile_benchmark
from .constants import CONSENT_LEVELS, MODES, OBJECT_TYPES, PERMISSIONS
from .database import KnowledgeDB
from .pipeline import create_pack, update_pack
from .schema_runtime import require_schema
from .utils import new_id, utc_now

JOB_FIELDS = {
    "distill": {
        "required": {"sources"},
        "allowed": {"sources", "type", "mode", "name", "access", "consent"},
    },
    "update": {
        "required": {"pack", "sources"},
        "allowed": {"pack", "sources"},
    },
    "benchmark": {
        "required": {"suite"},
        "allowed": {"suite", "output"},
    },
}
IDEMPOTENCY_KEY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)


def _workspace_path(
    workspace: Path,
    value: object,
    field: str,
    *,
    allow_url: bool = False,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty path")
    raw = value.strip()
    candidate = Path(raw).expanduser()
    if allow_url and not candidate.is_absolute():
        parsed = urlparse(raw)
        if parsed.scheme:
            if parsed.scheme not in {"http", "https"}:
                raise ValueError(f"{field} URL must use http or https")
            if not parsed.hostname or parsed.username or parsed.password:
                raise ValueError(f"{field} URL is invalid")
            return raw
    root = workspace.expanduser().resolve()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{field} must stay inside the workspace") from exc
    return str(resolved)


def _source_list(workspace: Path, value: object, *, required: bool) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("sources must be an array of paths or HTTP(S) URLs")
    if required and not value:
        raise ValueError("sources must not be empty")
    return [
        _workspace_path(workspace, item, "source", allow_url=True)
        for item in value
    ]


def validate_job_payload(
    workspace: Path,
    job_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate and normalize the local paths a persistent job may access."""
    require_schema(
        {"type": job_type, "payload": payload},
        "job-request.schema.json",
        "job request",
    )
    if job_type not in JOB_FIELDS:
        raise ValueError(f"unsupported job type: {job_type}")
    if not isinstance(payload, dict):
        raise ValueError("job payload must be an object")
    contract = JOB_FIELDS[job_type]
    fields = set(payload)
    missing = contract["required"] - fields
    unknown = fields - contract["allowed"]
    if missing:
        raise ValueError(f"job payload is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"job payload has unsupported fields: {', '.join(sorted(unknown))}")

    if job_type == "update":
        return {
            "pack": _workspace_path(workspace, payload["pack"], "pack"),
            "sources": _source_list(workspace, payload["sources"], required=False),
        }
    if job_type == "benchmark":
        normalized = {
            "suite": _workspace_path(workspace, payload["suite"], "suite"),
        }
        if payload.get("output") is not None:
            normalized["output"] = _workspace_path(
                workspace,
                payload["output"],
                "output",
            )
        return normalized

    profile = payload.get("type", "auto")
    mode = payload.get("mode", "standard")
    access = payload.get("access", "private-local")
    consent = payload.get("consent")
    name = payload.get("name")
    if profile not in OBJECT_TYPES:
        raise ValueError(f"unsupported distill type: {profile}")
    if mode not in MODES:
        raise ValueError(f"unsupported distill mode: {mode}")
    if access not in PERMISSIONS:
        raise ValueError(f"unsupported access level: {access}")
    if consent is not None and consent not in CONSENT_LEVELS:
        raise ValueError(f"unsupported consent level: {consent}")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise ValueError("name must be a non-empty string")
    return {
        "sources": _source_list(workspace, payload["sources"], required=True),
        "type": profile,
        "mode": mode,
        "name": name.strip() if isinstance(name, str) else None,
        "access": access,
        "consent": consent,
    }


class JobQueue:
    def __init__(self, database: KnowledgeDB):
        self.database = database
        self.workspace = (
            database.path.parent.parent
            if database.path.parent.name == ".one"
            else database.path.parent
        ).resolve()

    def audit(
        self,
        action: str,
        details: dict[str, Any],
        tenant_id: str = "local",
        actor_id: str = "local-user",
        asset_type: str | None = None,
        asset_id: str | None = None,
    ) -> str:
        return self.database.record_audit(
            tenant_id,
            actor_id,
            action,
            asset_type,
            asset_id,
            details,
        )

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        max_attempts: int = 3,
        actor_id: str = "local-user",
        idempotency_key: str | None = None,
    ) -> str:
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool):
            raise ValueError("max_attempts must be an integer")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        normalized = validate_job_payload(self.workspace, job_type, payload)
        if idempotency_key is not None and not IDEMPOTENCY_KEY_PATTERN.fullmatch(
            idempotency_key
        ):
            raise ValueError("idempotency_key is invalid")
        payload_json = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if idempotency_key is not None:
            existing = self.database.connection.execute(
                "SELECT id, job_type, payload_json, max_attempts FROM jobs "
                "WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                if (
                    existing["job_type"] != job_type
                    or existing["payload_json"] != payload_json
                    or existing["max_attempts"] != max_attempts
                ):
                    raise ValueError(
                        "idempotency_key was already used for a different job"
                    )
                self.audit(
                    "job.idempotent_replay",
                    {"job_type": job_type},
                    actor_id=actor_id,
                    asset_type="job",
                    asset_id=existing["id"],
                )
                return existing["id"]
        job_id = new_id("job")
        now = utc_now()
        try:
            self.database.connection.execute(
                "INSERT INTO jobs("
                "id, job_type, payload_json, status, attempts, max_attempts, "
                "idempotency_key, lease_token, lease_owner, lease_until, "
                "heartbeat_at, result_json, error, created_at, updated_at"
                ") VALUES (?, ?, ?, 'queued', 0, ?, ?, 0, NULL, NULL, NULL, "
                "NULL, NULL, ?, ?)",
                (
                    job_id,
                    job_type,
                    payload_json,
                    max_attempts,
                    idempotency_key,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            if idempotency_key is None:
                raise
            self.database.connection.rollback()
            existing = self.database.connection.execute(
                "SELECT id, job_type, payload_json, max_attempts FROM jobs "
                "WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if not existing:
                raise
            if (
                existing["job_type"] != job_type
                or existing["payload_json"] != payload_json
                or existing["max_attempts"] != max_attempts
            ):
                raise ValueError(
                    "idempotency_key was already used for a different job"
                )
            self.audit(
                "job.idempotent_replay",
                {"job_type": job_type},
                actor_id=actor_id,
                asset_type="job",
                asset_id=existing["id"],
            )
            return existing["id"]
        self.database.connection.commit()
        self.audit("job.enqueued", {"job_type": job_type}, actor_id=actor_id, asset_type="job", asset_id=job_id)
        return job_id

    def claim(self, owner: str, lease_seconds: int = 300) -> dict[str, Any] | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        connection = self.database.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                "SELECT * FROM jobs WHERE attempts < max_attempts AND "
                "(status = 'queued' OR (status = 'running' AND lease_until < ?)) "
                "ORDER BY created_at LIMIT 1",
                (now.isoformat(),),
            ).fetchone()
            if not row:
                connection.commit()
                return None
            connection.execute(
                "UPDATE jobs SET status = 'running', attempts = attempts + 1, "
                "lease_token = lease_token + 1, lease_owner = ?, lease_until = ?, "
                "heartbeat_at = ?, updated_at = ? WHERE id = ?",
                (
                    owner,
                    lease_until,
                    now.isoformat(),
                    now.isoformat(),
                    row["id"],
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        claimed = dict(row)
        claimed["attempts"] += 1
        claimed["lease_owner"] = owner
        claimed["lease_until"] = lease_until
        claimed["lease_token"] += 1
        claimed["heartbeat_at"] = now.isoformat()
        claimed["payload"] = json.loads(claimed.pop("payload_json"))
        self.audit("job.claimed", {"owner": owner}, actor_id=owner, asset_type="job", asset_id=claimed["id"])
        return claimed

    def heartbeat(
        self,
        job_id: str,
        owner: str,
        lease_token: int,
        lease_seconds: int = 300,
    ) -> str:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        now_value = now.isoformat()
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        cursor = self.database.connection.execute(
            "UPDATE jobs SET lease_until = ?, heartbeat_at = ?, updated_at = ? "
            "WHERE id = ? AND status = 'running' AND lease_owner = ? "
            "AND lease_token = ? AND lease_until >= ?",
            (
                lease_until,
                now_value,
                now_value,
                job_id,
                owner,
                lease_token,
                now_value,
            ),
        )
        if cursor.rowcount != 1:
            self.database.connection.rollback()
            raise ValueError("job heartbeat rejected: lease was lost")
        self.database.connection.commit()
        return lease_until

    def complete(
        self,
        job_id: str,
        owner: str,
        lease_token: int,
        result: dict[str, Any],
    ) -> None:
        now = utc_now()
        cursor = self.database.connection.execute(
            "UPDATE jobs SET status = 'completed', result_json = ?, lease_owner = NULL, "
            "lease_until = NULL, heartbeat_at = NULL, updated_at = ? "
            "WHERE id = ? AND status = 'running' AND lease_owner = ? "
            "AND lease_token = ? AND lease_until >= ?",
            (
                json.dumps(result, ensure_ascii=False),
                now,
                job_id,
                owner,
                lease_token,
                now,
            ),
        )
        if cursor.rowcount != 1:
            self.database.connection.rollback()
            raise ValueError("job completion rejected: lease owner or state mismatch")
        self.database.connection.commit()
        self.audit("job.completed", result, actor_id=owner, asset_type="job", asset_id=job_id)

    def fail(
        self,
        job_id: str,
        owner: str,
        lease_token: int,
        error: str,
    ) -> None:
        now = utc_now()
        row = self.database.connection.execute(
            "SELECT attempts, max_attempts FROM jobs "
            "WHERE id = ? AND lease_owner = ? AND lease_token = ? "
            "AND lease_until >= ?",
            (job_id, owner, lease_token, now),
        ).fetchone()
        if not row:
            raise ValueError("job failure rejected: lease owner mismatch")
        status = "failed" if row["attempts"] >= row["max_attempts"] else "queued"
        cursor = self.database.connection.execute(
            "UPDATE jobs SET status = ?, error = ?, lease_owner = NULL, "
            "lease_until = NULL, heartbeat_at = NULL, updated_at = ? "
            "WHERE id = ? AND lease_token = ?",
            (status, error, now, job_id, lease_token),
        )
        if cursor.rowcount != 1:
            self.database.connection.rollback()
            raise ValueError("job failure rejected: lease was lost")
        self.database.connection.commit()
        self.audit("job.failed", {"error": error, "next_status": status}, actor_id=owner, asset_type="job", asset_id=job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        row = self.database.connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise ValueError(f"job does not exist: {job_id}")
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["result"] = json.loads(result["result_json"]) if result["result_json"] else None
        return result


class _LeaseHeartbeat:
    def __init__(
        self,
        database_path: Path,
        job_id: str,
        owner: str,
        lease_token: int,
        lease_seconds: int,
    ):
        self.database_path = database_path
        self.job_id = job_id
        self.owner = owner
        self.lease_token = lease_token
        self.lease_seconds = lease_seconds
        self.stop_event = Event()
        self.error: Exception | None = None
        self.thread = Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        interval = max(0.25, min(10.0, self.lease_seconds / 3))
        while not self.stop_event.wait(interval):
            try:
                with KnowledgeDB(self.database_path) as database:
                    JobQueue(database).heartbeat(
                        self.job_id,
                        self.owner,
                        self.lease_token,
                        self.lease_seconds,
                    )
            except (sqlite3.Error, OSError, RuntimeError, ValueError) as exc:
                self.error = exc
                self.stop_event.set()

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(1.0, self.lease_seconds))


def run_worker_once(
    workspace: Path,
    owner: str,
    lease_seconds: int = 300,
) -> dict[str, Any] | None:
    database_path = workspace / ".one" / "knowledge.db"
    with KnowledgeDB(database_path) as database:
        queue = JobQueue(database)
        job = queue.claim(owner, lease_seconds)
        if job is None:
            return None
        heartbeat = _LeaseHeartbeat(
            database_path,
            job["id"],
            owner,
            job["lease_token"],
            lease_seconds,
        )
        heartbeat.start()
        try:
            payload = validate_job_payload(workspace, job["job_type"], job["payload"])
            if job["job_type"] == "distill":
                pack = create_pack(
                    workspace,
                    payload["sources"],
                    payload.get("type", "auto"),
                    payload.get("mode", "standard"),
                    payload.get("name"),
                    payload.get("access", "private-local"),
                    payload.get("consent"),
                )
                result = {"pack": str(pack)}
            elif job["job_type"] == "update":
                result = update_pack(Path(payload["pack"]), payload["sources"])
            else:
                result = run_profile_benchmark(
                    Path(payload["suite"]),
                    Path(payload["output"]) if payload.get("output") else None,
                )
            heartbeat.stop()
            if heartbeat.error is not None:
                raise RuntimeError(f"job lease heartbeat failed: {heartbeat.error}")
            queue.complete(job["id"], owner, job["lease_token"], result)
            return {"job_id": job["id"], "status": "completed", "result": result}
        except (OSError, RuntimeError, ValueError) as exc:
            heartbeat.stop()
            try:
                queue.fail(
                    job["id"],
                    owner,
                    job["lease_token"],
                    f"{type(exc).__name__}: {exc}",
                )
            except ValueError as lease_error:
                return {
                    "job_id": job["id"],
                    "status": "lease-lost",
                    "error": str(lease_error),
                }
            return {"job_id": job["id"], "status": "failed", "error": str(exc)}
        finally:
            heartbeat.stop()
