"""Deterministic Pack metadata migrations that never invent semantic artifacts."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from .comparison import judge_artifact_hash
from .locking import pack_lock
from .provenance import source_set_fingerprint
from .schema_runtime import require_schema, validate_schema
from .utils import atomic_write, dump_json, load_json, stable_json_hash, utc_now
from .versions import CURRENT_PACK_VERSION, READABLE_PACK_VERSIONS


class MigrationError(ValueError):
    pass


MIGRATION_ID = "pack-schema-1.0"
LEGACY_ASSETS = (
    "RECIPE_LOCK.json",
    "PROTECTED_CONSTRAINTS.json",
    "PIPELINE_STATE.json",
    "PIPELINE_STATE.md",
    "SOURCE_QUALITY.json",
    "OBJECT_MAP.md",
)


def _upgrade_semantic_metadata(pack: Path, metadata: dict[str, Any]) -> None:
    overview = pack / "OBJECT_OVERVIEW.json"
    portfolio = pack / "VERIFIED_PORTFOLIO.json"
    graph = pack / "CAPABILITY_GRAPH.json"
    metadata["semantic_contract"] = {
        "overview_confirmation": "confirmed" if overview.exists() else "stale",
        "capability_confirmation": "confirmed" if portfolio.exists() else "stale",
    }
    metadata["object_overview_hash"] = (
        stable_json_hash(load_json(overview)) if overview.exists() else None
    )
    metadata["capability_portfolio_hash"] = (
        stable_json_hash(load_json(portfolio)) if portfolio.exists() else None
    )
    metadata["capability_graph_hash"] = (
        stable_json_hash(load_json(graph)) if graph.exists() else None
    )


def _migration_paths(pack: Path) -> tuple[Path, Path]:
    root = pack / "audit" / "migrations" / MIGRATION_ID
    return root / "journal.json", root / "backup"


def _prepare_journal(
    pack: Path,
    original_version: str,
) -> tuple[Path, Path, dict[str, Any]]:
    journal_path, backup_root = _migration_paths(pack)
    if journal_path.exists():
        return journal_path, backup_root, load_json(journal_path)
    originals = [
        relative
        for relative in ("pack.json", "SOURCE_MANIFEST.json", *LEGACY_ASSETS)
        if (pack / relative).exists()
    ]
    for relative in originals:
        source = pack / relative
        destination = backup_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    journal = {
        "schema_version": "1.0",
        "id": MIGRATION_ID,
        "from": original_version,
        "to": CURRENT_PACK_VERSION,
        "status": "pending",
        "original_files": originals,
        "removed_legacy_assets": [],
        "started_at": utc_now(),
    }
    dump_json(journal_path, journal)
    return journal_path, backup_root, journal


def _remove_legacy_asset(path: Path) -> None:
    path.unlink()


def _evaluation_contract_is_current(pack: Path) -> bool:
    assets = [
        *sorted((pack / "evaluations" / "runs").glob("*.json")),
        pack / "evaluations" / "comparison-report.json",
    ]
    artifacts_current = all(
        not path.exists()
        or not validate_schema(
            load_json(path),
            (
                "comparison-report.schema.json"
                if path.name == "comparison-report.json"
                else "evaluation-run.schema.json"
            ),
        )
        for path in assets
    )
    results_path = pack / "test-results.json"
    results_current = (
        not results_path.exists()
        or load_json(results_path).get("status") in {"valid", "stale"}
    )
    return artifacts_current and results_current


def _backup_evaluation_assets(
    pack: Path,
    journal_path: Path,
    backup_root: Path,
    journal: dict[str, Any],
) -> None:
    assets = [
        *sorted((pack / "evaluations" / "runs").glob("*.json")),
        pack / "evaluations" / "comparison-report.json",
        pack / "test-results.json",
    ]
    originals = set(journal.get("original_files", []))
    for source in assets:
        if not source.is_file():
            continue
        relative = source.relative_to(pack).as_posix()
        if relative in originals:
            continue
        destination = backup_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        originals.add(relative)
    journal["original_files"] = sorted(originals)
    dump_json(journal_path, journal)


def _normalize_evaluation_contract(
    pack: Path,
    manifest: dict[str, Any],
    reproducibility: dict[str, Any],
) -> None:
    run_paths = sorted((pack / "evaluations" / "runs").glob("*.json"))
    report_path = pack / "evaluations" / "comparison-report.json"
    if not run_paths:
        if report_path.exists():
            raise MigrationError(
                "comparison report exists without evaluation run artifacts"
            )
        results_path = pack / "test-results.json"
        if results_path.exists():
            results = load_json(results_path)
            results.setdefault("status", "valid")
            dump_json(results_path, results)
        return
    current_source_hash = source_set_fingerprint(manifest)
    legacy_source_hash = stable_json_hash(
        reproducibility.get("source_hashes", {})
    )
    can_rebind_source_hash = all(
        item.get("active", True) and not item.get("revoked_at")
        for item in manifest.get("sources", [])
    )
    runs: dict[str, dict[str, Any]] = {}
    for path in run_paths:
        run = load_json(path)
        existing_artifact_hash = run.get("artifact_hash")
        if existing_artifact_hash is not None:
            artifact = dict(run)
            artifact.pop("artifact_hash", None)
            if existing_artifact_hash != stable_json_hash(artifact):
                raise MigrationError(
                    f"evaluation artifact hash is invalid before migration: {path}"
                )
        old_source_hash = run.get("source_set_hash")
        if old_source_hash not in {legacy_source_hash, current_source_hash}:
            raise MigrationError(
                f"evaluation source hash is unrelated to Pack provenance: {path}"
            )
        source_hash = (
            current_source_hash if can_rebind_source_hash else old_source_hash
        )
        for record in run.get("records", []):
            hashes = record.setdefault("hashes", {})
            if hashes.get("source_set") not in {
                legacy_source_hash,
                current_source_hash,
            }:
                raise MigrationError(
                    f"evaluation record source hash is invalid: {path}"
                )
            answer_hash = hashlib.sha256(
                str(record.get("answer") or "").encode("utf-8")
            ).hexdigest()
            if (
                hashes.get("answer") is not None
                and hashes.get("answer") != answer_hash
            ):
                raise MigrationError(
                    f"evaluation answer hash is invalid before migration: {path}"
                )
            judge_hash = judge_artifact_hash(
                bool(record.get("passed")),
                record.get("scores", {}),
                str(record.get("judge_reason") or ""),
            )
            if (
                hashes.get("judge") is not None
                and hashes.get("judge") != judge_hash
            ):
                raise MigrationError(
                    f"evaluation judge hash is invalid before migration: {path}"
                )
            hashes["source_set"] = source_hash
            hashes["answer"] = answer_hash
            hashes["judge"] = judge_hash
        run["source_set_hash"] = source_hash
        run.setdefault("runtime", "one-skills/migrated-pack-1.0")
        run.setdefault("parameters", {"migration": MIGRATION_ID})
        run["input_snapshot_hash"] = stable_json_hash(
            {
                "suite": run["suite_hash"],
                "source_set": source_hash,
                "skill": run["skill_hash"],
            }
        )
        run.pop("artifact_hash", None)
        run["artifact_hash"] = stable_json_hash(run)
        require_schema(run, "evaluation-run.schema.json", str(path))
        dump_json(path, run)
        runs[run["condition"]] = run

    if report_path.exists():
        report = load_json(report_path)
        candidate = runs.get("one-skills")
        if candidate is None:
            raise MigrationError("comparison report has no candidate run")
        if can_rebind_source_hash:
            report["source_set_hash"] = current_source_hash
            report.setdefault("status", "valid")
        else:
            report["status"] = "stale"
            report.setdefault(
                "stale_reason",
                "source state changed before evaluation contract migration",
            )
            report.setdefault("stale_at", utc_now())
        report["isolation_level"] = candidate["isolation_level"]
        report["candidate_run_hash"] = candidate["artifact_hash"]
        report["run_hashes"] = {
            condition: run["artifact_hash"]
            for condition, run in sorted(runs.items())
        }
        require_schema(
            report,
            "comparison-report.schema.json",
            str(report_path),
        )
        dump_json(report_path, report)
    results_path = pack / "test-results.json"
    if results_path.exists():
        results = load_json(results_path)
        results.setdefault(
            "status",
            "valid" if can_rebind_source_hash else "stale",
        )
        dump_json(results_path, results)


def migrate_pack(pack: Path) -> dict[str, Any]:
    metadata_path = pack / "pack.json"
    if not metadata_path.exists():
        raise MigrationError(f"missing Pack metadata: {metadata_path}")
    with pack_lock(pack):
        metadata = load_json(metadata_path)
        version = metadata.get("schema_version")
        if version not in READABLE_PACK_VERSIONS:
            raise MigrationError(f"unsupported Pack schema: {version}")
        existing_journal, _ = _migration_paths(pack)
        reproducibility = metadata.get("reproducibility")
        has_source_set_hash = (
            isinstance(reproducibility, dict)
            and isinstance(reproducibility.get("source_set_hash"), str)
        )
        evaluation_contract_current = _evaluation_contract_is_current(pack)
        if existing_journal.exists() and not evaluation_contract_current:
            existing_state = load_json(existing_journal)
            if (
                existing_state.get("status") == "completed"
                and metadata.get("revision")
                != existing_state.get("result_revision")
            ):
                raise MigrationError(
                    "Pack changed after migration; refusing to rewrite "
                    "newer evaluation artifacts"
                )
        if (
            version == CURRENT_PACK_VERSION
            and has_source_set_hash
            and evaluation_contract_current
            and not existing_journal.exists()
            and not any((pack / relative).exists() for relative in LEGACY_ASSETS)
        ):
            return {
                "status": "unchanged",
                "schema_version": CURRENT_PACK_VERSION,
                "pack": str(pack),
            }
        if (
            version == CURRENT_PACK_VERSION
            and has_source_set_hash
            and evaluation_contract_current
            and existing_journal.exists()
            and load_json(existing_journal).get("status") == "completed"
            and not any((pack / relative).exists() for relative in LEGACY_ASSETS)
        ):
            return {
                "status": "unchanged",
                "schema_version": CURRENT_PACK_VERSION,
                "pack": str(pack),
            }
        original_version = (
            load_json(existing_journal).get("from", version)
            if existing_journal.exists()
            else version
        )
        journal_path, backup_root, journal = _prepare_journal(
            pack,
            original_version,
        )
        try:
            if original_version == "0.2" and "semantic_contract" not in metadata:
                _upgrade_semantic_metadata(pack, metadata)
            required = {
                "recipe_lock": pack / "RECIPE_LOCK.json",
                "reproducibility": pack / "PROTECTED_CONSTRAINTS.json",
                "lifecycle": pack / "PIPELINE_STATE.json",
            }
            if original_version in {"0.2", "0.3"}:
                missing = [
                    name
                    for name, path in required.items()
                    if name not in metadata and not path.exists()
                ]
                if missing:
                    raise MigrationError(
                        "legacy Pack is missing consolidation inputs: "
                        + ", ".join(missing)
                    )
                for name, path in required.items():
                    if name not in metadata:
                        metadata[name] = load_json(path)

            lifecycle = metadata.get("lifecycle")
            if not isinstance(lifecycle, dict):
                raise MigrationError("Pack lifecycle is missing or invalid")
            lifecycle["schema_version"] = "1.0"
            metadata["lifecycle"] = lifecycle
            migrated_at = metadata.get("migrated_at") or utc_now()
            history = metadata.setdefault("migration_history", [])
            migration_record = {
                "from": original_version,
                "to": CURRENT_PACK_VERSION,
                "migrated_at": migrated_at,
            }
            if original_version != CURRENT_PACK_VERSION and migration_record not in history:
                history.append(migration_record)
            metadata["schema_version"] = CURRENT_PACK_VERSION
            metadata["migrated_at"] = migrated_at
            metadata["revision"] = int(metadata.get("revision", 0)) + 1

            manifest_path = pack / "SOURCE_MANIFEST.json"
            manifest = load_json(manifest_path)
            quality_path = pack / "SOURCE_QUALITY.json"
            manifest["schema_version"] = "1.0"
            if "quality" not in manifest:
                manifest["quality"] = (
                    load_json(quality_path) if quality_path.exists() else {}
                )
            reproducibility = metadata.get("reproducibility")
            if not isinstance(reproducibility, dict):
                raise MigrationError("Pack reproducibility contract is invalid")
            reproducibility["source_set_hash"] = source_set_fingerprint(
                manifest
            )
            metadata["reproducibility"] = reproducibility
            if not evaluation_contract_current:
                _backup_evaluation_assets(
                    pack,
                    journal_path,
                    backup_root,
                    journal,
                )
                _normalize_evaluation_contract(
                    pack,
                    manifest,
                    reproducibility,
                )
            require_schema(metadata, "pack.schema.json", str(metadata_path))
            require_schema(
                manifest,
                "source-manifest.schema.json",
                str(manifest_path),
            )
            journal["status"] = "committing"
            journal["updated_at"] = utc_now()
            dump_json(journal_path, journal)
            dump_json(manifest_path, manifest)
            dump_json(metadata_path, metadata)

            removed = set(journal.get("removed_legacy_assets", []))
            for relative in LEGACY_ASSETS:
                path = pack / relative
                if path.exists():
                    _remove_legacy_asset(path)
                    removed.add(relative)
                    journal["removed_legacy_assets"] = sorted(removed)
                    dump_json(journal_path, journal)
            journal["status"] = "completed"
            journal["completed_at"] = utc_now()
            journal["result_revision"] = metadata["revision"]
            journal.pop("last_error", None)
            dump_json(journal_path, journal)
        except Exception as exc:
            journal["status"] = "pending"
            journal["last_error"] = f"{type(exc).__name__}: {exc}"
            journal["updated_at"] = utc_now()
            dump_json(journal_path, journal)
            raise
        return {
            "status": "migrated",
            "schema_version": CURRENT_PACK_VERSION,
            "pack": str(pack),
            "semantic_contract": metadata["semantic_contract"],
            "removed_legacy_assets": journal["removed_legacy_assets"],
            "requires_rebuild": not all(
                (
                    (pack / "OBJECT_OVERVIEW.json").exists(),
                    (pack / "VERIFIED_PORTFOLIO.json").exists(),
                    (pack / "CAPABILITY_GRAPH.json").exists(),
                )
            ),
        }


def rollback_pack_migration(pack: Path) -> dict[str, Any]:
    with pack_lock(pack):
        journal_path, backup_root = _migration_paths(pack)
        if not journal_path.exists():
            raise MigrationError("Pack has no 1.0 migration journal")
        journal = load_json(journal_path)
        metadata = load_json(pack / "pack.json")
        result_revision = journal.get("result_revision")
        if (
            result_revision is not None
            and metadata.get("revision") != result_revision
        ):
            raise MigrationError(
                "Pack changed after migration; rollback would discard newer work"
            )
        originals = journal.get("original_files", [])
        if not isinstance(originals, list) or "pack.json" not in originals:
            raise MigrationError("migration backup is incomplete")
        for relative in originals:
            backup = backup_root / relative
            if not backup.is_file():
                raise MigrationError(f"migration backup is missing: {relative}")
        for relative in originals:
            backup = backup_root / relative
            atomic_write(pack / relative, backup.read_text(encoding="utf-8"))
        journal["status"] = "rolled_back"
        journal["rolled_back_at"] = utc_now()
        dump_json(journal_path, journal)
        return {
            "status": "rolled_back",
            "schema_version": journal["from"],
            "pack": str(pack),
        }


def migrate_pack_to_v04(pack: Path) -> dict[str, Any]:
    """Compatibility alias; all supported legacy Packs now converge on 1.0."""
    return migrate_pack(pack)


def migrate_pack_to_v03(pack: Path) -> dict[str, Any]:
    """Compatibility alias; all supported legacy Packs now converge on 1.0."""
    return migrate_pack(pack)
