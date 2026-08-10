"""Canonical Pack assets and compatibility readers for consolidated Packs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import dump_json, load_json

CONSOLIDATED_PACK_VERSION = "0.4"

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
    dump_json(pack / "pack.json", metadata)


def is_consolidated_pack(pack: Path) -> bool:
    metadata_path = pack / "pack.json"
    return (
        metadata_path.exists()
        and load_json(metadata_path).get("schema_version") == CONSOLIDATED_PACK_VERSION
    )


def load_recipe_lock(pack: Path) -> dict[str, Any]:
    metadata = load_pack_metadata(pack)
    if metadata.get("schema_version") == CONSOLIDATED_PACK_VERSION:
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
    if metadata.get("schema_version") == CONSOLIDATED_PACK_VERSION:
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
    if metadata.get("schema_version") == CONSOLIDATED_PACK_VERSION:
        metadata["reproducibility"] = value
        save_pack_metadata(pack, metadata)
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
    dump_json(
        pack / "SOURCE_MANIFEST.json",
        {
            "schema_version": "1.0",
            "profile": profile,
            "quality": quality,
            "sources": sources,
        },
    )


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
