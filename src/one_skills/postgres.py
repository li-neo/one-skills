"""Optional PostgreSQL + pgvector migration and verification backend."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

from .retrieval import local_embedding

MIGRATION_TABLES = (
    "tenants",
    "principals",
    "sources",
    "source_assessments",
    "documents",
    "document_versions",
    "chunks",
    "claims",
    "evidence_links",
    "capabilities",
    "lineage_edges",
    "skill_versions",
    "eval_runs",
    "person_subjects",
    "person_facts",
    "person_evidence_links",
    "runs",
    "jobs",
    "audit_events",
    "asset_acl",
)


class PostgresBackend:
    def __init__(self, dsn: str):
        try:
            import psycopg
            from psycopg import sql
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL backend requires `pip install one-skills[production]`"
            ) from exc
        self.sql = sql
        self.Jsonb = Jsonb
        self.connection = psycopg.connect(dsn, row_factory=dict_row)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "PostgresBackend":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def initialize(self, migration_path: Path) -> None:
        sql = migration_path.read_text(encoding="utf-8")
        with self.connection.cursor() as cursor:
            cursor.execute(sql)
        self.connection.commit()

    def health(self) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT current_database() AS database, version() AS version")
            server = cursor.fetchone()
            cursor.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            vector = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS count FROM chunks")
            chunks = cursor.fetchone()["count"]
        return {
            "database": server["database"],
            "server_version": server["version"],
            "pgvector_version": vector["extversion"] if vector else None,
            "chunks": chunks,
            "ready": vector is not None,
        }

    def migrate_from_sqlite(self, sqlite_path: Path, batch_size: int = 500) -> dict[str, int]:
        source = sqlite3.connect(sqlite_path)
        source.row_factory = sqlite3.Row
        counts: dict[str, int] = {}
        try:
            for table in MIGRATION_TABLES:
                exists = source.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()
                if not exists:
                    continue
                rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
                if not rows:
                    counts[table] = 0
                    continue
                columns = list(rows[0].keys())
                statement = self.sql.SQL(
                    "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING"
                ).format(
                    self.sql.Identifier(table),
                    self.sql.SQL(", ").join(
                        self.sql.Identifier(column) for column in columns
                    ),
                    self.sql.SQL(", ").join(
                        self.sql.SQL("{}::vector").format(self.sql.Placeholder())
                        if column == "embedding"
                        and table in {"chunks", "person_facts"}
                        else self.sql.Placeholder()
                        for column in columns
                    ),
                )
                inserted = 0
                with self.connection.cursor() as cursor:
                    for offset in range(0, len(rows), batch_size):
                        batch = [
                            tuple(self._convert_value(table, column, row[column]) for column in columns)
                            for row in rows[offset : offset + batch_size]
                        ]
                        cursor.executemany(statement, batch)
                        inserted += len(batch)
                self.connection.commit()
                counts[table] = inserted
        finally:
            source.close()
        return counts

    def _convert_value(self, table: str, column: str, value: Any) -> Any:
        if value is None:
            return None
        if column == "embedding" and table in {"chunks", "person_facts"}:
            parsed = json.loads(value) if isinstance(value, str) else value
            if not parsed:
                return None
            if len(parsed) != 128:
                raise ValueError(f"{table}.{column} must contain 128 dimensions")
            return self._vector_literal(parsed)
        if column in {
            "ir_json",
            "input_json",
            "output_json",
            "payload_json",
            "result_json",
            "details_json",
            "quality_json",
        }:
            parsed = json.loads(value) if isinstance(value, str) else value
            return self.Jsonb(parsed)
        if column in {
            "captured_at",
            "created_at",
            "updated_at",
            "valid_from",
            "valid_to",
            "lease_until",
        } and isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(str(float(item)) for item in values) + "]"

    def hybrid_search(
        self,
        query: str,
        allowed_access: set[str],
        tenant_id: str,
        principal_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        vector = "[" + ",".join(str(value) for value in local_embedding(query)) + "]"
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                WITH permitted AS (
                  SELECT c.*
                  FROM chunks c
                  JOIN documents d
                    ON d.id = c.document_id AND d.active_version = c.document_version
                  WHERE c.access_level = ANY(%s)
                    AND EXISTS (
                      SELECT 1 FROM asset_acl acl
                      WHERE acl.asset_type = 'chunk' AND acl.asset_id = c.id
                        AND acl.tenant_id = %s
                        AND acl.principal_id IN (%s, '*')
                        AND acl.permission IN ('read', 'owner')
                    )
                ),
                ranked AS (
                  SELECT *,
                    ts_rank_cd(search_vector, plainto_tsquery('simple', %s)) AS text_score,
                    1 - (embedding <=> %s::vector) AS vector_score
                  FROM permitted
                )
                SELECT *,
                  (text_score * 0.45 + GREATEST(vector_score, 0) * 0.55) AS score
                FROM ranked
                WHERE text_score > 0 OR vector_score >= 0.20
                ORDER BY score DESC
                LIMIT %s
                """,
                (list(allowed_access), tenant_id, principal_id, query, vector, limit),
            )
            return list(cursor.fetchall())

    def load_test(
        self,
        query: str,
        iterations: int = 100,
        tenant_id: str = "local",
        principal_id: str = "local-user",
    ) -> dict[str, Any]:
        if iterations < 1:
            raise ValueError("iterations must be positive")
        timings = []
        result_count = 0
        for _ in range(iterations):
            started = perf_counter()
            results = self.hybrid_search(
                query,
                {"public", "authorized", "private-local"},
                tenant_id,
                principal_id,
            )
            timings.append((perf_counter() - started) * 1000)
            result_count = len(results)
        ordered = sorted(timings)
        p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95))
        return {
            "iterations": iterations,
            "result_count": result_count,
            "p50_ms": round(median(ordered), 3),
            "p95_ms": round(ordered[p95_index], 3),
            "max_ms": round(max(ordered), 3),
        }
