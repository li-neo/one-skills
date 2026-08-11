"""SQLite knowledge, lineage, memory, and run-state storage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import Chunk, SourceDocument
from .utils import new_id, utc_now

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  uri TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  media_type TEXT NOT NULL,
  access_level TEXT NOT NULL,
  license TEXT,
  captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_assessments (
  source_id TEXT PRIMARY KEY REFERENCES sources(id),
  authority TEXT NOT NULL,
  directness TEXT NOT NULL,
  independence_group TEXT NOT NULL,
  source_role TEXT NOT NULL,
  source_uri TEXT,
  creator TEXT,
  published_at TEXT,
  quality_score REAL NOT NULL,
  quality_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  type TEXT NOT NULL,
  owner TEXT,
  access_level TEXT NOT NULL,
  active_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS document_versions (
  document_id TEXT NOT NULL REFERENCES documents(id),
  version INTEGER NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(id),
  source_hash TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  normalized_uri TEXT,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (document_id, version)
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  document_version INTEGER NOT NULL,
  section_path TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  access_level TEXT NOT NULL,
  source_locator TEXT NOT NULL,
  embedding TEXT,
  UNIQUE(document_id, document_version, ordinal)
);

CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY,
  statement TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL,
  valid_from TEXT,
  valid_to TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_links (
  claim_id TEXT NOT NULL REFERENCES claims(id),
  chunk_id TEXT NOT NULL REFERENCES chunks(id),
  relation TEXT NOT NULL,
  quote_start INTEGER,
  quote_end INTEGER,
  PRIMARY KEY (claim_id, chunk_id, relation)
);

CREATE TABLE IF NOT EXISTS capabilities (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  profile TEXT NOT NULL,
  ir_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lineage_edges (
  from_type TEXT NOT NULL,
  from_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  to_type TEXT NOT NULL,
  to_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (from_type, from_id, relation, to_type, to_id)
);

CREATE TABLE IF NOT EXISTS graph_edges (
  pack_id TEXT NOT NULL,
  from_type TEXT NOT NULL,
  from_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  to_type TEXT NOT NULL,
  to_id TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL,
  confidence REAL NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (pack_id, from_type, from_id, relation, to_type, to_id)
);

CREATE TABLE IF NOT EXISTS skill_versions (
  skill_id TEXT NOT NULL,
  version TEXT NOT NULL,
  recipe_version TEXT NOT NULL,
  ir_hash TEXT NOT NULL,
  artifact_uri TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (skill_id, version)
);

CREATE TABLE IF NOT EXISTS eval_runs (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  suite_version TEXT NOT NULL,
  result_uri TEXT NOT NULL,
  passed INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person_subjects (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  relation TEXT,
  access_level TEXT NOT NULL,
  active_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person_facts (
  id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES person_subjects(id),
  dimension TEXT NOT NULL,
  statement TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL,
  valid_from TEXT,
  valid_to TEXT,
  supersedes TEXT REFERENCES person_facts(id),
  embedding TEXT,
  access_level TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person_evidence_links (
  fact_id TEXT NOT NULL REFERENCES person_facts(id),
  chunk_id TEXT NOT NULL REFERENCES chunks(id),
  relation TEXT NOT NULL,
  PRIMARY KEY (fact_id, chunk_id, relation)
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  pack_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  status TEXT NOT NULL,
  input_json TEXT NOT NULL,
  output_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  lease_owner TEXT,
  lease_until TEXT,
  result_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  asset_type TEXT,
  asset_id TEXT,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS principals (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS asset_acl (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  principal_id TEXT NOT NULL,
  asset_type TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  permission TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, principal_id, asset_type, asset_id, permission)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id, document_version);
CREATE INDEX IF NOT EXISTS idx_chunks_access ON chunks(access_level);
CREATE INDEX IF NOT EXISTS idx_person_facts_subject ON person_facts(subject_id, status);
CREATE INDEX IF NOT EXISTS idx_edges_from ON lineage_edges(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON lineage_edges(to_type, to_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_pack ON graph_edges(pack_id, from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_acl_asset ON asset_acl(tenant_id, asset_type, asset_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_asset ON audit_events(asset_type, asset_id, created_at);
"""


class KnowledgeDB:
    """Owns a SQLite connection and keeps all derived indexes transactional."""

    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        now = utc_now()
        self.connection.execute(
            "INSERT OR IGNORE INTO tenants VALUES ('local', 'Local workspace', ?)", (now,)
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO principals VALUES ('local', 'local-user', 'Local user', ?)",
            (now,),
        )
        self.connection.commit()
        self.fts_enabled = self._create_fts()

    def _create_fts(self) -> bool:
        try:
            self.connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts "
                "USING fts5(chunk_id UNINDEXED, text, section_path)"
            )
            self.connection.commit()
            return True
        except sqlite3.OperationalError:
            return False

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "KnowledgeDB":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def add_document(
        self,
        source: SourceDocument,
        document_type: str,
        normalized_uri: str | None = None,
    ) -> tuple[str, str, int, bool]:
        existing = self.connection.execute(
            "SELECT id FROM sources WHERE content_hash = ?", (source.content_hash,)
        ).fetchone()
        if existing:
            self.connection.execute(
                "INSERT OR REPLACE INTO source_assessments VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    existing["id"],
                    source.authority,
                    source.directness,
                    source.independence_group or source.source,
                    source.source_role,
                    source.source_uri,
                    source.creator,
                    source.published_at,
                    source.quality_score,
                    json.dumps(source.metadata(), ensure_ascii=False),
                ),
            )
            self.connection.commit()
            linked = self.connection.execute(
                "SELECT document_id, version FROM document_versions "
                "WHERE source_id = ? ORDER BY version DESC LIMIT 1",
                (existing["id"],),
            ).fetchone()
            if linked:
                return existing["id"], linked["document_id"], linked["version"], False

        source_id = new_id("source")
        now = utc_now()
        previous = self.connection.execute(
            "SELECT dv.document_id, MAX(dv.version) AS version "
            "FROM sources s JOIN document_versions dv ON dv.source_id = s.id "
            "WHERE s.uri = ? GROUP BY dv.document_id ORDER BY version DESC LIMIT 1",
            (source.source,),
        ).fetchone()
        document_id = previous["document_id"] if previous else new_id("document")
        version = int(previous["version"]) + 1 if previous else 1
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id,
                    source.source,
                    source.content_hash,
                    source.media_type,
                    source.access_level,
                    source.license,
                    now,
                ),
            )
            connection.execute(
                "INSERT INTO source_assessments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id,
                    source.authority,
                    source.directness,
                    source.independence_group or source.source,
                    source.source_role,
                    source.source_uri,
                    source.creator,
                    source.published_at,
                    source.quality_score,
                    json.dumps(source.metadata(), ensure_ascii=False),
                ),
            )
            if previous:
                connection.execute(
                    "UPDATE documents SET title = ?, type = ?, access_level = ?, active_version = ? "
                    "WHERE id = ?",
                    (source.title, document_type, source.access_level, version, document_id),
                )
                connection.execute(
                    "UPDATE document_versions SET status = 'superseded' "
                    "WHERE document_id = ? AND status = 'active'",
                    (document_id,),
                )
            else:
                connection.execute(
                    "INSERT INTO documents(id, title, type, access_level, active_version) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (document_id, source.title, document_type, source.access_level),
                )
            connection.execute(
                "INSERT INTO document_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    document_id,
                    version,
                    source_id,
                    source.content_hash,
                    "one-skills@0.3",
                    normalized_uri,
                    "active",
                    now,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO lineage_edges VALUES (?, ?, ?, ?, ?, ?)",
                ("source", source_id, "produces", "document", document_id, now),
            )
        return source_id, document_id, version, True

    def ingest_document(
        self,
        source: SourceDocument,
        document_type: str,
        chunk_builder: Callable[[str, int], list[Chunk]],
        embedding_builder: Callable[[list[Chunk]], dict[str, list[float]]],
        normalized_uri_builder: Callable[[str, int], str | None] | None = None,
    ) -> tuple[str, str, int, bool, list[Chunk]]:
        """Commit a complete searchable document before switching active_version."""
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                "SELECT id FROM sources WHERE content_hash = ?",
                (source.content_hash,),
            ).fetchone()
            if existing:
                linked = connection.execute(
                    "SELECT document_id, version FROM document_versions "
                    "WHERE source_id = ? ORDER BY version DESC LIMIT 1",
                    (existing["id"],),
                ).fetchone()
                if linked:
                    chunks = chunk_builder(
                        linked["document_id"],
                        linked["version"],
                    )
                    embeddings = embedding_builder(chunks)
                    normalized_uri = (
                        normalized_uri_builder(
                            linked["document_id"],
                            linked["version"],
                        )
                        if normalized_uri_builder
                        else None
                    )
                    connection.execute(
                        "INSERT OR REPLACE INTO source_assessments VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            existing["id"],
                            source.authority,
                            source.directness,
                            source.independence_group or source.source,
                            source.source_role,
                            source.source_uri,
                            source.creator,
                            source.published_at,
                            source.quality_score,
                            json.dumps(source.metadata(), ensure_ascii=False),
                        ),
                    )
                    if normalized_uri is not None:
                        connection.execute(
                            "UPDATE document_versions SET normalized_uri = ? "
                            "WHERE document_id = ? AND version = ?",
                            (
                                normalized_uri,
                                linked["document_id"],
                                linked["version"],
                            ),
                        )
                    self._insert_chunks(connection, chunks, embeddings, ignore_existing=True)
                    connection.commit()
                    return (
                        existing["id"],
                        linked["document_id"],
                        linked["version"],
                        False,
                        chunks,
                    )

            source_id = new_id("source")
            now = utc_now()
            previous = connection.execute(
                "SELECT dv.document_id, MAX(dv.version) AS version "
                "FROM sources s JOIN document_versions dv ON dv.source_id = s.id "
                "WHERE s.uri = ? GROUP BY dv.document_id "
                "ORDER BY version DESC LIMIT 1",
                (source.source,),
            ).fetchone()
            document_id = previous["document_id"] if previous else new_id("document")
            version = int(previous["version"]) + 1 if previous else 1
            chunks = chunk_builder(document_id, version)
            if not chunks:
                raise ValueError("document produced no searchable chunks")
            embeddings = embedding_builder(chunks)
            normalized_uri = (
                normalized_uri_builder(document_id, version)
                if normalized_uri_builder
                else None
            )
            connection.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id,
                    source.source,
                    source.content_hash,
                    source.media_type,
                    source.access_level,
                    source.license,
                    now,
                ),
            )
            connection.execute(
                "INSERT INTO source_assessments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id,
                    source.authority,
                    source.directness,
                    source.independence_group or source.source,
                    source.source_role,
                    source.source_uri,
                    source.creator,
                    source.published_at,
                    source.quality_score,
                    json.dumps(source.metadata(), ensure_ascii=False),
                ),
            )
            if previous:
                connection.execute(
                    "UPDATE documents SET title = ?, type = ?, access_level = ? "
                    "WHERE id = ?",
                    (
                        source.title,
                        document_type,
                        source.access_level,
                        document_id,
                    ),
                )
            else:
                connection.execute(
                    "INSERT INTO documents"
                    "(id, title, type, access_level, active_version) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (
                        document_id,
                        source.title,
                        document_type,
                        source.access_level,
                    ),
                )
            connection.execute(
                "INSERT INTO document_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    document_id,
                    version,
                    source_id,
                    source.content_hash,
                    "one-skills@1.0",
                    normalized_uri,
                    "staging",
                    now,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO lineage_edges VALUES (?, ?, ?, ?, ?, ?)",
                ("source", source_id, "produces", "document", document_id, now),
            )
            self._insert_chunks(connection, chunks, embeddings)
            if previous:
                connection.execute(
                    "UPDATE document_versions SET status = 'superseded' "
                    "WHERE document_id = ? AND status = 'active'",
                    (document_id,),
                )
            connection.execute(
                "UPDATE documents SET active_version = ? WHERE id = ?",
                (version, document_id),
            )
            connection.execute(
                "UPDATE document_versions SET status = 'active' "
                "WHERE document_id = ? AND version = ?",
                (document_id, version),
            )
            connection.commit()
            return source_id, document_id, version, True, chunks
        except Exception:
            connection.rollback()
            raise

    def _insert_chunks(
        self,
        connection: sqlite3.Connection,
        chunks: list[Chunk],
        embeddings: dict[str, list[float]],
        *,
        ignore_existing: bool = False,
    ) -> None:
        insert = "INSERT OR IGNORE" if ignore_existing else "INSERT"
        for chunk in chunks:
            cursor = connection.execute(
                f"{insert} INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk.id,
                    chunk.document_id,
                    chunk.document_version,
                    chunk.section_path,
                    chunk.ordinal,
                    chunk.text,
                    chunk.content_hash,
                    len(chunk.text.split()),
                    chunk.access_level,
                    chunk.source_locator,
                    json.dumps(embeddings.get(chunk.id, [])),
                ),
            )
            if cursor.rowcount == 0:
                continue
            if self.fts_enabled:
                connection.execute(
                    "DELETE FROM chunks_fts WHERE chunk_id = ?",
                    (chunk.id,),
                )
                connection.execute(
                    "INSERT INTO chunks_fts(chunk_id, text, section_path) "
                    "VALUES (?, ?, ?)",
                    (chunk.id, chunk.text, chunk.section_path),
                )
            connection.execute(
                "INSERT OR IGNORE INTO lineage_edges VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "document",
                    chunk.document_id,
                    "produces",
                    "chunk",
                    chunk.id,
                    utc_now(),
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO asset_acl VALUES "
                "('local', 'local-user', 'chunk', ?, 'owner', ?)",
                (chunk.id, utc_now()),
            )

    def add_chunks(self, chunks: list[Chunk], embeddings: dict[str, list[float]]) -> None:
        with self.transaction() as connection:
            self._insert_chunks(connection, chunks, embeddings, ignore_existing=True)

    def invalidate_claims_from_inactive_versions(self) -> int:
        """Supersede claims supported only by inactive document versions."""
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE claims SET status = 'superseded' "
                "WHERE status = 'active' AND id IN ("
                "SELECT DISTINCT el.claim_id FROM evidence_links el "
                "JOIN chunks c ON c.id = el.chunk_id "
                "JOIN documents d ON d.id = c.document_id "
                "WHERE c.document_version <> d.active_version"
                ") AND id NOT IN ("
                "SELECT DISTINCT el.claim_id FROM evidence_links el "
                "JOIN chunks c ON c.id = el.chunk_id "
                "JOIN documents d ON d.id = c.document_id "
                "WHERE c.document_version = d.active_version"
                ")"
            )
        return cursor.rowcount

    def add_claim(
        self,
        statement: str,
        confidence: float,
        chunk_ids: list[str],
        status: str = "active",
        claim_id: str | None = None,
    ) -> str:
        claim_id = claim_id or new_id("claim")
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO claims VALUES (?, ?, ?, ?, NULL, NULL, ?)",
                (claim_id, statement, status, confidence, utc_now()),
            )
            for chunk_id in chunk_ids:
                connection.execute(
                    "INSERT INTO evidence_links VALUES (?, ?, 'supports', NULL, NULL)",
                    (claim_id, chunk_id),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO lineage_edges VALUES (?, ?, ?, ?, ?, ?)",
                    ("chunk", chunk_id, "supports", "claim", claim_id, utc_now()),
                )
        return claim_id

    def add_capability(self, capability_id: str, name: str, profile: str, ir: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO capabilities VALUES (?, ?, ?, ?, 'active', ?)",
            (capability_id, name, profile, json.dumps(ir, ensure_ascii=False), utc_now()),
        )
        self.connection.commit()

    def add_edge(
        self,
        from_type: str,
        from_id: str,
        relation: str,
        to_type: str,
        to_id: str,
    ) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO lineage_edges VALUES (?, ?, ?, ?, ?, ?)",
            (from_type, from_id, relation, to_type, to_id, utc_now()),
        )
        self.connection.commit()

    def add_graph_edge(
        self,
        pack_id: str,
        from_type: str,
        from_id: str,
        relation: str,
        to_type: str,
        to_id: str,
        evidence_ids: list[str],
        confidence: float,
        status: str,
    ) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO graph_edges VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pack_id,
                from_type,
                from_id,
                relation,
                to_type,
                to_id,
                json.dumps(evidence_ids, ensure_ascii=False),
                confidence,
                status,
                utc_now(),
            ),
        )
        self.connection.commit()

    def clear_pack_graph(self, pack_id: str) -> None:
        self.connection.execute(
            "DELETE FROM graph_edges WHERE pack_id = ?",
            (pack_id,),
        )
        self.connection.commit()

    def add_person_subject(
        self,
        display_name: str,
        relation: str,
        access_level: str = "private-local",
    ) -> str:
        subject_id = new_id("person")
        self.connection.execute(
            "INSERT INTO person_subjects VALUES (?, ?, ?, ?, 1, ?)",
            (subject_id, display_name, relation, access_level, utc_now()),
        )
        self.connection.commit()
        return subject_id

    def mutate_person_fact(
        self,
        action: str,
        subject_id: str,
        dimension: str,
        statement: str,
        confidence: float,
        access_level: str,
        supersedes: str | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        if action not in {"ADD", "UPDATE", "REVOKE"}:
            raise ValueError("person fact action must be ADD, UPDATE, or REVOKE")
        now = utc_now()
        fact_id = new_id("fact")
        with self.transaction() as connection:
            if action in {"UPDATE", "REVOKE"}:
                if not supersedes:
                    raise ValueError(f"{action} requires supersedes")
                target = connection.execute(
                    "SELECT id FROM person_facts WHERE id = ? AND subject_id = ?",
                    (supersedes, subject_id),
                ).fetchone()
                if not target:
                    raise ValueError("superseded person fact does not exist")
                connection.execute(
                    "UPDATE person_facts SET status = ?, valid_to = ?, updated_at = ? WHERE id = ?",
                    ("superseded" if action == "UPDATE" else "revoked", now, now, supersedes),
                )
            if action != "REVOKE":
                connection.execute(
                    "INSERT INTO person_facts VALUES (?, ?, ?, ?, 'active', ?, ?, NULL, ?, ?, ?, ?)",
                    (
                        fact_id,
                        subject_id,
                        dimension,
                        statement,
                        confidence,
                        now,
                        supersedes,
                        json.dumps(embedding or []),
                        access_level,
                        now,
                    ),
                )
        return fact_id if action != "REVOKE" else supersedes or ""

    def rows(self, query: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(query, parameters).fetchall())

    def create_tenant(self, tenant_id: str, name: str) -> None:
        self.connection.execute(
            "INSERT INTO tenants VALUES (?, ?, ?)",
            (tenant_id, name, utc_now()),
        )
        self.connection.commit()

    def create_principal(self, tenant_id: str, principal_id: str, display_name: str) -> None:
        self.connection.execute(
            "INSERT INTO principals VALUES (?, ?, ?, ?)",
            (tenant_id, principal_id, display_name, utc_now()),
        )
        self.connection.commit()

    def grant_acl(
        self,
        tenant_id: str,
        principal_id: str,
        asset_type: str,
        asset_id: str,
        permission: str,
    ) -> None:
        if permission not in {"read", "write", "owner"}:
            raise ValueError("ACL permission must be read, write, or owner")
        tenant = self.connection.execute(
            "SELECT id FROM tenants WHERE id = ?", (tenant_id,)
        ).fetchone()
        if not tenant:
            raise ValueError(f"tenant does not exist: {tenant_id}")
        if principal_id != "*":
            principal = self.connection.execute(
                "SELECT id FROM principals WHERE tenant_id = ? AND id = ?",
                (tenant_id, principal_id),
            ).fetchone()
            if not principal:
                raise ValueError(f"principal does not exist: {tenant_id}/{principal_id}")
        self.connection.execute(
            "INSERT OR IGNORE INTO asset_acl VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, principal_id, asset_type, asset_id, permission, utc_now()),
        )
        self.connection.commit()
        self.record_audit(
            tenant_id,
            "local-user",
            "acl.granted",
            asset_type,
            asset_id,
            {"principal_id": principal_id, "permission": permission},
        )

    def record_audit(
        self,
        tenant_id: str,
        actor_id: str,
        action: str,
        asset_type: str | None,
        asset_id: str | None,
        details: dict[str, Any],
    ) -> str:
        event_id = new_id("audit")
        self.connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                tenant_id,
                actor_id,
                action,
                asset_type,
                asset_id,
                json.dumps(details, ensure_ascii=False),
                utc_now(),
            ),
        )
        self.connection.commit()
        return event_id

    def descendants(self, node_type: str, node_id: str) -> list[dict[str, str]]:
        queue = [(node_type, node_id)]
        seen = set(queue)
        result: list[dict[str, str]] = []
        while queue:
            current_type, current_id = queue.pop(0)
            edges = self.rows(
                "SELECT relation, to_type, to_id FROM lineage_edges "
                "WHERE from_type = ? AND from_id = ?",
                (current_type, current_id),
            )
            for edge in edges:
                target = (edge["to_type"], edge["to_id"])
                if target in seen:
                    continue
                seen.add(target)
                queue.append(target)
                result.append(
                    {
                        "from_type": current_type,
                        "from_id": current_id,
                        "relation": edge["relation"],
                        "to_type": edge["to_type"],
                        "to_id": edge["to_id"],
                    }
                )
        return result

    def revoke_source(self, source_id: str) -> dict[str, Any]:
        source = self.connection.execute(
            "SELECT id, uri FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        if not source:
            raise ValueError(f"source does not exist: {source_id}")
        affected = self.descendants("source", source_id)
        document_ids = {
            edge["to_id"] for edge in affected if edge["to_type"] == "document"
        }
        with self.transaction() as connection:
            for document_id in document_ids:
                connection.execute(
                    "UPDATE document_versions SET status = 'revoked' "
                    "WHERE document_id = ? AND source_id = ?",
                    (document_id, source_id),
                )
                active = connection.execute(
                    "SELECT MAX(version) AS version FROM document_versions "
                    "WHERE document_id = ? AND status = 'active'",
                    (document_id,),
                ).fetchone()
                connection.execute(
                    "UPDATE documents SET active_version = ? WHERE id = ?",
                    (active["version"] or 0, document_id),
                )
        self.record_audit(
            "local",
            "local-user",
            "source.revoked",
            "source",
            source_id,
            {"uri": source["uri"], "affected_count": len(affected)},
        )
        return {
            "source_id": source_id,
            "uri": source["uri"],
            "affected": affected,
        }
