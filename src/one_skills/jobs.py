"""Persistent leased job queue and append-only audit events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from .benchmark import run_profile_benchmark
from .database import KnowledgeDB
from .pipeline import create_pack, update_pack
from .utils import new_id, utc_now


class JobQueue:
    def __init__(self, database: KnowledgeDB):
        self.database = database

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
    ) -> str:
        if job_type not in {"distill", "update", "benchmark"}:
            raise ValueError(f"unsupported job type: {job_type}")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        job_id = new_id("job")
        now = utc_now()
        self.database.connection.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, 'queued', 0, ?, NULL, NULL, NULL, NULL, ?, ?)",
            (job_id, job_type, json.dumps(payload, ensure_ascii=False), max_attempts, now, now),
        )
        self.database.connection.commit()
        self.audit("job.enqueued", {"job_type": job_type}, actor_id=actor_id, asset_type="job", asset_id=job_id)
        return job_id

    def claim(self, owner: str, lease_seconds: int = 300) -> dict[str, Any] | None:
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
                "lease_owner = ?, lease_until = ?, updated_at = ? WHERE id = ?",
                (owner, lease_until, now.isoformat(), row["id"]),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        claimed = dict(row)
        claimed["attempts"] += 1
        claimed["lease_owner"] = owner
        claimed["lease_until"] = lease_until
        claimed["payload"] = json.loads(claimed.pop("payload_json"))
        self.audit("job.claimed", {"owner": owner}, actor_id=owner, asset_type="job", asset_id=claimed["id"])
        return claimed

    def complete(self, job_id: str, owner: str, result: dict[str, Any]) -> None:
        cursor = self.database.connection.execute(
            "UPDATE jobs SET status = 'completed', result_json = ?, lease_owner = NULL, "
            "lease_until = NULL, updated_at = ? "
            "WHERE id = ? AND status = 'running' AND lease_owner = ?",
            (json.dumps(result, ensure_ascii=False), utc_now(), job_id, owner),
        )
        if cursor.rowcount != 1:
            raise ValueError("job completion rejected: lease owner or state mismatch")
        self.database.connection.commit()
        self.audit("job.completed", result, actor_id=owner, asset_type="job", asset_id=job_id)

    def fail(self, job_id: str, owner: str, error: str) -> None:
        row = self.database.connection.execute(
            "SELECT attempts, max_attempts FROM jobs WHERE id = ? AND lease_owner = ?",
            (job_id, owner),
        ).fetchone()
        if not row:
            raise ValueError("job failure rejected: lease owner mismatch")
        status = "failed" if row["attempts"] >= row["max_attempts"] else "queued"
        self.database.connection.execute(
            "UPDATE jobs SET status = ?, error = ?, lease_owner = NULL, lease_until = NULL, "
            "updated_at = ? WHERE id = ?",
            (status, error, utc_now(), job_id),
        )
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


def run_worker_once(workspace: Path, owner: str) -> dict[str, Any] | None:
    database_path = workspace / ".one" / "knowledge.db"
    with KnowledgeDB(database_path) as database:
        queue = JobQueue(database)
        job = queue.claim(owner)
        if job is None:
            return None
        try:
            payload = job["payload"]
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
            queue.complete(job["id"], owner, result)
            return {"job_id": job["id"], "status": "completed", "result": result}
        except (OSError, RuntimeError, ValueError) as exc:
            queue.fail(job["id"], owner, f"{type(exc).__name__}: {exc}")
            return {"job_id": job["id"], "status": "failed", "error": str(exc)}
