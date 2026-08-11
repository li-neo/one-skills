"""Canonical Pack assets and compatibility readers for consolidated Packs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .locking import pack_lock
from .schema_runtime import require_schema
from .utils import dump_json, load_json
from .versions import CURRENT_PACK_VERSION, uses_consolidated_assets

CONSOLIDATED_PACK_VERSION = CURRENT_PACK_VERSION

AUTHORITATIVE_ASSETS = (
    "pack.json",
    "SOURCE_MANIFEST.json",
    "OBJECT_OVERVIEW.json",
    "EVIDENCE_LEDGER.jsonl",
    "VERIFIED_PORTFOLIO.json",
    "evaluations/",
)

INTERMEDIATE_ASSETS = (
    "candidates/",
    "verified/",
    "rejected/",
    "CANDIDATE_PORTFOLIO.json",
)

DERIVED_ASSETS = (
    "DISTILLATION_CONTRACT.md",
    "CANDIDATE_OUTPUT.md",
    "CANDIDATE_PORTFOLIO.md",
    "OBJECT_OVERVIEW.md",
    "VERIFIED_PORTFOLIO.md",
    "CAPABILITY_GRAPH.json",
    "LEARNING_PATH.json",
    "GLOSSARY.md",
    "DIGEST.md",
    "INDEX.md",
    "MODEL_CARD.md",
    "test-results.json",
    "reports/",
    "skills/",
)


class ConcurrentPackUpdateError(RuntimeError):
    pass


def _default_reproducibility() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_hashes": {},
        "protected": ["canonical_evals", "negative_tests"],
        "canonical_eval_hashes": {},
        "runtime_eval_hashes": {},
        "evaluation_suite_hashes": {},
        "skill_hashes": {},
    }


def load_pack_metadata(pack: Path) -> dict[str, Any]:
    return load_json(pack / "pack.json")


def save_pack_metadata(pack: Path, metadata: dict[str, Any]) -> None:
    with pack_lock(pack):
        path = pack / "pack.json"
        current = load_json(path) if path.exists() else {}
        current_revision = int(current.get("revision", 0))
        expected_revision = metadata.get("revision")
        if (
            expected_revision is not None
            and int(expected_revision) != current_revision
        ):
            raise ConcurrentPackUpdateError(
                f"Pack revision changed: expected {expected_revision}, "
                f"found {current_revision}"
            )
        metadata["revision"] = current_revision + 1
        require_schema(metadata, "pack.schema.json", str(path))
        dump_json(path, metadata)


def update_pack_metadata(
    pack: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Apply one locked metadata mutation without overwriting sibling fields."""
    with pack_lock(pack):
        metadata = load_pack_metadata(pack)
        revision = int(metadata.get("revision", 0))
        mutate(metadata)
        metadata["revision"] = revision + 1
        require_schema(
            metadata,
            "pack.schema.json",
            str(pack / "pack.json"),
        )
        dump_json(pack / "pack.json", metadata)
        return metadata


def is_consolidated_pack(pack: Path) -> bool:
    metadata_path = pack / "pack.json"
    return (
        metadata_path.exists()
        and uses_consolidated_assets(
            load_json(metadata_path).get("schema_version")
        )
    )


def load_recipe_lock(pack: Path) -> dict[str, Any]:
    metadata = load_pack_metadata(pack)
    if uses_consolidated_assets(metadata.get("schema_version")):
        value = metadata.get("recipe_lock")
        if not isinstance(value, dict):
            raise ValueError("consolidated Pack is missing recipe_lock")
        return value
    return load_json(pack / "RECIPE_LOCK.json")


def load_reproducibility(pack: Path) -> dict[str, Any]:
    metadata_path = pack / "pack.json"
    if not metadata_path.exists():
        legacy = pack / "PROTECTED_CONSTRAINTS.json"
        return load_json(legacy) if legacy.exists() else _default_reproducibility()
    metadata = load_json(metadata_path)
    if uses_consolidated_assets(metadata.get("schema_version")):
        value = metadata.get("reproducibility")
        if not isinstance(value, dict):
            raise ValueError("consolidated Pack is missing reproducibility")
        return value
    return load_json(pack / "PROTECTED_CONSTRAINTS.json")


def save_reproducibility(pack: Path, value: dict[str, Any]) -> None:
    metadata_path = pack / "pack.json"
    if not metadata_path.exists():
        dump_json(pack / "PROTECTED_CONSTRAINTS.json", value)
        return
    metadata = load_json(metadata_path)
    if uses_consolidated_assets(metadata.get("schema_version")):
        update_pack_metadata(
            pack,
            lambda current: current.__setitem__("reproducibility", value),
        )
        return
    dump_json(pack / "PROTECTED_CONSTRAINTS.json", value)


def load_source_manifest(pack: Path) -> dict[str, Any]:
    return load_json(pack / "SOURCE_MANIFEST.json")


def load_source_quality(pack: Path) -> dict[str, Any]:
    manifest = load_source_manifest(pack)
    quality = manifest.get("quality")
    if isinstance(quality, dict):
        return quality
    quality_path = pack / "SOURCE_QUALITY.json"
    return load_json(quality_path) if quality_path.exists() else {}


def save_source_manifest(
    pack: Path,
    *,
    profile: str,
    sources: list[dict[str, Any]],
    quality: dict[str, Any],
) -> None:
    value = {
        "schema_version": "1.0",
        "profile": profile,
        "quality": quality,
        "sources": sources,
    }
    require_schema(
        value,
        "source-manifest.schema.json",
        str(pack / "SOURCE_MANIFEST.json"),
    )
    dump_json(pack / "SOURCE_MANIFEST.json", value)


def artifact_contract(pack: Path) -> dict[str, Any]:
    metadata = load_pack_metadata(pack)
    return {
        "pack_schema": metadata.get("schema_version"),
        "authoritative": list(AUTHORITATIVE_ASSETS),
        "intermediate": list(INTERMEDIATE_ASSETS),
        "derived": list(DERIVED_ASSETS),
        "rule": (
            "Authoritative assets may update derived projections; derived projections "
            "must never overwrite authoritative assets."
        ),
    }
