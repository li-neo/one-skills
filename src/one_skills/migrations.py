"""Deterministic Pack metadata migrations that never invent semantic artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import dump_json, load_json, stable_json_hash, utc_now


class MigrationError(ValueError):
    pass


def migrate_pack_to_v03(pack: Path) -> dict[str, Any]:
    metadata_path = pack / "pack.json"
    if not metadata_path.exists():
        raise MigrationError(f"missing Pack metadata: {metadata_path}")
    metadata = load_json(metadata_path)
    version = metadata.get("schema_version")
    if version == "0.3":
        return {"status": "unchanged", "schema_version": "0.3", "pack": str(pack)}
    if version != "0.2":
        raise MigrationError(f"unsupported Pack schema: {version}")

    overview = pack / "OBJECT_OVERVIEW.json"
    portfolio = pack / "VERIFIED_PORTFOLIO.json"
    graph = pack / "CAPABILITY_GRAPH.json"
    metadata["schema_version"] = "0.3"
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
    metadata["migrated_at"] = utc_now()
    dump_json(metadata_path, metadata)
    return {
        "status": "migrated",
        "schema_version": "0.3",
        "pack": str(pack),
        "semantic_contract": metadata["semantic_contract"],
        "requires_rebuild": not all((overview.exists(), portfolio.exists(), graph.exists())),
    }
