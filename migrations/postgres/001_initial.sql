CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  uri TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  media_type TEXT NOT NULL,
  access_level TEXT NOT NULL,
  license TEXT,
  captured_at TIMESTAMPTZ NOT NULL
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
  quality_score DOUBLE PRECISION NOT NULL,
  quality_json JSONB NOT NULL
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
  created_at TIMESTAMPTZ NOT NULL,
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
  embedding vector(128),
  search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
  UNIQUE(document_id, document_version, ordinal)
);

CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY,
  statement TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL
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
  ir_json JSONB NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS lineage_edges (
  from_type TEXT NOT NULL,
  from_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  to_type TEXT NOT NULL,
  to_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (from_type, from_id, relation, to_type, to_id)
);

CREATE TABLE IF NOT EXISTS skill_versions (
  skill_id TEXT NOT NULL,
  version TEXT NOT NULL,
  recipe_version TEXT NOT NULL,
  ir_hash TEXT NOT NULL,
  artifact_uri TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (skill_id, version)
);

CREATE TABLE IF NOT EXISTS eval_runs (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  suite_version TEXT NOT NULL,
  result_uri TEXT NOT NULL,
  passed INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS person_subjects (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  relation TEXT,
  access_level TEXT NOT NULL,
  active_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS person_facts (
  id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES person_subjects(id),
  dimension TEXT NOT NULL,
  statement TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  supersedes TEXT REFERENCES person_facts(id),
  embedding vector(128),
  access_level TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS person_evidence_links (
  fact_id TEXT NOT NULL REFERENCES person_facts(id),
  chunk_id TEXT NOT NULL REFERENCES chunks(id),
  relation TEXT NOT NULL,
  PRIMARY KEY (fact_id, chunk_id, relation)
);

CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS principals (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS asset_acl (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  principal_id TEXT NOT NULL,
  asset_type TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  permission TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, principal_id, asset_type, asset_id, permission)
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  pack_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  status TEXT NOT NULL,
  input_json JSONB NOT NULL,
  output_json JSONB,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  lease_owner TEXT,
  lease_until TIMESTAMPTZ,
  result_json JSONB,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  asset_type TEXT,
  asset_id TEXT,
  details_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_search ON chunks USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_access ON chunks(access_level);
CREATE INDEX IF NOT EXISTS idx_edges_from ON lineage_edges(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON lineage_edges(to_type, to_id);
CREATE INDEX IF NOT EXISTS idx_acl_asset ON asset_acl(tenant_id, asset_type, asset_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_asset ON audit_events(asset_type, asset_id, created_at);
