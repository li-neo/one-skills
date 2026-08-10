"""Deterministic Pack metadata migrations that never invent semantic artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core_assets import CONSOLIDATED_PACK_VERSION
from .utils import dump_json, load_json, stable_json_hash, utc_now


class MigrationError(ValueError):
    pass


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


def migrate_pack_to_v04(pack: Path) -> dict[str, Any]:
    metadata_path = pack / "pack.json"
    if not metadata_path.exists():
        raise MigrationError(f"missing Pack metadata: {metadata_path}")
    metadata = load_json(metadata_path)
    version = metadata.get("schema_version")
    if version == CONSOLIDATED_PACK_VERSION:
        lifecycle = metadata.get("lifecycle", {})
        if isinstance(lifecycle, dict) and lifecycle.get("schema_version") != "1.0":
            lifecycle["schema_version"] = "1.0"
            metadata["lifecycle"] = lifecycle
            metadata["migrated_at"] = utc_now()
            dump_json(metadata_path, metadata)
            return {
                "status": "normalized",
                "schema_version": CONSOLIDATED_PACK_VERSION,
                "pack": str(pack),
            }
        return {
            "status": "unchanged",
            "schema_version": CONSOLIDATED_PACK_VERSION,
            "pack": str(pack),
        }
    if version not in {"0.2", "0.3"}:
        raise MigrationError(f"unsupported Pack schema: {version}")

    if version == "0.2":
        _upgrade_semantic_metadata(pack, metadata)

    required = {
        "recipe_lock": pack / "RECIPE_LOCK.json",
        "reproducibility": pack / "PROTECTED_CONSTRAINTS.json",
        "lifecycle": pack / "PIPELINE_STATE.json",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise MigrationError(
            "legacy Pack is missing consolidation inputs: " + ", ".join(missing)
        )
    metadata["schema_version"] = CONSOLIDATED_PACK_VERSION
    metadata["recipe_lock"] = load_json(required["recipe_lock"])
    metadata["reproducibility"] = load_json(required["reproducibility"])
    metadata["lifecycle"] = load_json(required["lifecycle"])
    metadata["lifecycle"]["schema_version"] = "1.0"
    metadata["migrated_at"] = utc_now()

    manifest_path = pack / "SOURCE_MANIFEST.json"
    manifest = load_json(manifest_path)
    quality_path = pack / "SOURCE_QUALITY.json"
    manifest["schema_version"] = "1.0"
    manifest["quality"] = (
        load_json(quality_path)
        if quality_path.exists()
        else manifest.get("quality", {})
    )
    dump_json(manifest_path, manifest)
    dump_json(metadata_path, metadata)

    removed: list[str] = []
    for relative in (
        "RECIPE_LOCK.json",
        "PROTECTED_CONSTRAINTS.json",
        "PIPELINE_STATE.json",
        "PIPELINE_STATE.md",
        "SOURCE_QUALITY.json",
        "OBJECT_MAP.md",
    ):
        path = pack / relative
        if path.exists():
            path.unlink()
            removed.append(relative)
    return {
        "status": "migrated",
        "schema_version": CONSOLIDATED_PACK_VERSION,
        "pack": str(pack),
        "semantic_contract": metadata["semantic_contract"],
        "removed_legacy_assets": removed,
        "requires_rebuild": not all(
            (
                (pack / "OBJECT_OVERVIEW.json").exists(),
                (pack / "VERIFIED_PORTFOLIO.json").exists(),
                (pack / "CAPABILITY_GRAPH.json").exists(),
            )
        ),
    }


def migrate_pack_to_v03(pack: Path) -> dict[str, Any]:
    """Compatibility alias; current migrations converge on the v0.4 core."""
    return migrate_pack_to_v04(pack)
