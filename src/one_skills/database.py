"""SQLite knowledge, lineage, memory, and run-state storage."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

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

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id, document_version);
CREATE INDEX IF NOT EXISTS idx_chunks_access ON chunks(access_level);
CREATE INDEX IF NOT EXISTS idx_person_facts_subject ON person_facts(subject_id, status);
CREATE INDEX IF NOT EXISTS idx_edges_from ON lineage_edges(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON lineage_edges(to_type, to_id);
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
            linked = self.connection.execute(
                "SELECT document_id, version FROM document_versions "
                "WHERE source_id = ? ORDER BY version DESC LIMIT 1",
                (existing["id"],),
            ).fetchone()
            if linked:
                return existing["id"], linked["document_id"], linked["version"], False

        source_id = new_id("source")
        document_id = new_id("document")
        now = utc_now()
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
                "INSERT INTO documents(id, title, type, access_level, active_version) "
                "VALUES (?, ?, ?, ?, 1)",
                (document_id, source.title, document_type, source.access_level),
            )
            connection.execute(
                "INSERT INTO document_versions VALUES (?, 1, ?, ?, ?, ?, ?, ?)",
                (
                    document_id,
                    source_id,
                    source.content_hash,
                    "one-skills@0.1",
                    normalized_uri,
                    "active",
                    now,
                ),
            )
        return source_id, document_id, 1, True

    def add_chunks(self, chunks: list[Chunk], embeddings: dict[str, list[float]]) -> None:
        with self.transaction() as connection:
            for chunk in chunks:
                connection.execute(
                    "INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                if self.fts_enabled:
                    connection.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk.id,))
                    connection.execute(
                        "INSERT INTO chunks_fts(chunk_id, text, section_path) VALUES (?, ?, ?)",
                        (chunk.id, chunk.text, chunk.section_path),
                    )

    def add_claim(
        self,
        statement: str,
        confidence: float,
        chunk_ids: list[str],
        status: str = "active",
    ) -> str:
        claim_id = new_id("claim")
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
