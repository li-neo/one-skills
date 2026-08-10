"""Deterministic reliability, completeness, and accuracy gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core_assets import (
    load_pack_metadata,
    load_reproducibility,
    load_source_manifest,
)
from .lifecycle import load_state
from .utils import load_json

DEPLOYABLE_DISPOSITIONS = {
    "independent-module",
    "shared-principle",
    "governance",
}

EXECUTABLE_FIELDS = (
    "problem",
    "assumptions",
    "triggers",
    "anti_triggers",
    "procedure",
    "output",
    "done",
    "boundaries",
    "failures",
)


def _rate(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 1.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _evidence_items(pack: Path) -> dict[str, dict[str, Any]]:
    path = pack / "EVIDENCE_LEDGER.jsonl"
    if not path.exists():
        return {}
    values: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("id"):
            values[str(item["id"])] = item
    return values


def assess_distillation_quality(pack: Path) -> dict[str, Any]:
    metadata = load_pack_metadata(pack)
    state = load_state(pack)
    manifest = load_source_manifest(pack)
    constraints = load_reproducibility(pack)
    sources = manifest.get("sources", [])
    expected_hashes = {
        f"{item['source_id']}@{item['document_version']}": item["content_hash"]
        for item in sources
        if {"source_id", "document_version", "content_hash"} <= set(item)
    }
    source_hash_consistent = constraints.get("source_hashes") == expected_hashes

    overview_path = pack / "OBJECT_OVERVIEW.json"
    overview = load_json(overview_path) if overview_path.exists() else {}
    overview_complete = bool(
        overview.get("status") == "confirmed"
        and overview.get("thesis")
        and overview.get("structure")
        and overview.get("limitations")
    )

    portfolio_path = pack / "VERIFIED_PORTFOLIO.json"
    portfolio = load_json(portfolio_path) if portfolio_path.exists() else {}
    portfolio_confirmed = portfolio.get("status") == "confirmed"
    candidates = [
        item
        for item in portfolio.get("candidates", [])
        if item.get("status") != "rejected"
        and item.get("disposition") in DEPLOYABLE_DISPOSITIONS
    ]
    accepted = [item for item in candidates if item.get("status") == "accepted"]

    deployable_ids = {candidate["id"] for candidate in candidates}
    research_coverage = _rate(
        [
            bool(deployable_ids & set(ids))
            for ids in portfolio.get("coverage", {}).values()
        ]
    )
    executable_coverage = _rate(
        [
            all(bool(candidate.get(field)) for field in EXECUTABLE_FIELDS)
            for candidate in candidates
        ]
    )

    evidence_items = _evidence_items(pack)
    chunks_path = pack / "sources" / "chunks.json"
    active_chunk_ids = {
        item["id"]
        for item in load_json(chunks_path)
    } if chunks_path.exists() else set()

    def evidence_resolves(evidence_id: str) -> bool:
        item = evidence_items.get(evidence_id)
        if not item or not item.get("source") or not item.get("locator"):
            return False
        chunk_id = item.get("chunk_id")
        return not chunk_id or chunk_id in active_chunk_ids

    evidence_resolution = _rate(
        [
            bool(candidate.get("evidence_ids"))
            and all(evidence_resolves(value) for value in candidate["evidence_ids"])
            for candidate in candidates
        ]
    )
    independent_support = _rate(
        [
            len(set(candidate.get("independence_groups", []))) >= 2
            for candidate in accepted
        ]
    )
    verified_accuracy = _rate(
        [
            all(
                bool(candidate.get(field))
                for field in (
                    "cross_domain",
                    "predictive",
                    "distinctive",
                    "actionable",
                )
            )
            and bool(candidate.get("boundaries"))
            for candidate in accepted
        ]
    )

    reliability = _mean(
        [
            float(source_hash_consistent),
            evidence_resolution,
            float(bool(metadata.get("recipe"))),
        ]
    )
    completeness = _mean(
        [
            float(overview_complete),
            research_coverage,
            executable_coverage,
        ]
    )
    accuracy = _mean(
        [
            evidence_resolution,
            independent_support,
            verified_accuracy,
        ]
    )
    hard_gates = {
        "source_hash_consistent": source_hash_consistent,
        "overview_confirmed": overview_complete,
        "portfolio_confirmed": portfolio_confirmed,
        "research_coverage_complete": research_coverage == 1.0,
        "capabilities_executable": executable_coverage == 1.0,
        "evidence_resolved": evidence_resolution == 1.0,
        "accepted_capabilities_independent": independent_support == 1.0,
        "accepted_capabilities_verified": verified_accuracy == 1.0,
    }
    ready_phase = state["current_phase"] in {"test", "ship", "evolve"}
    passed = ready_phase and all(hard_gates.values())
    return {
        "schema_version": "1.0",
        "status": "passed" if passed else "failed" if ready_phase else "pending",
        "passed": passed,
        "dimensions": {
            "reliability": round(reliability, 4),
            "completeness": round(completeness, 4),
            "accuracy": round(accuracy, 4),
        },
        "hard_gates": hard_gates,
        "counts": {
            "sources": len(sources),
            "evidence": len(evidence_items),
            "deployable_capabilities": len(candidates),
            "accepted_capabilities": len(accepted),
        },
    }
