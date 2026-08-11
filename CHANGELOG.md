# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/) and
Semantic Versioning.

## [1.0.0] - 2026-08-11

### Added

- Stable local CLI and Pack 1.0 contract.
- Runtime JSON Schema validation for Pack, provenance, evaluation, Job, and
  evolution artifacts.
- Recoverable migration registry for Pack 0.2, 0.3, and 0.4.
- Atomic document ingestion, Pack staging, cross-process locking, revision
  checks, and intent-first source revocation.
- Source Set, Suite, Skill, Answer, Judge, and evaluation artifact hashes.
- Job idempotency keys, lease heartbeat, and fencing tokens.
- MIT license, security policy, packaged Schemas, PostgreSQL migration, and
  isolated artifact checks.

### Changed

- New Packs write Schema 1.0.
- Source ingestion is all-or-nothing by default.
- Source updates invalidate every chunk-bound evidence type and stale prior
  evaluation reports.
- Stable Pack delivery requires provider-separated or model-separated
  evaluation; shared-model sessions remain development evidence.
- PostgreSQL repeat migration now UPSERTs mutable state.

### Security

- Prevented Evolution snapshot path escape and unsafe rollback.
- Bound API search identity to server configuration.
- Restricted Job filesystem access to its workspace.
- Added fail-closed revocation and delivery behavior.

## [0.4.0] - 2026-08-10

### Added

- Consolidated lifecycle, Recipe Lock, reproducibility, and Source Quality.
- Reliability, completeness, and accuracy hard gates.

[1.0.0]: https://github.com/li-neo/one-skills/compare/b396727eb0bf49b5e1b3fa41b0b2a545545980f2...v1.0.0
[0.4.0]: https://github.com/li-neo/one-skills/commits/b396727eb0bf49b5e1b3fa41b0b2a545545980f2
