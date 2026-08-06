"""Deterministic source-set planning and quality gates."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import SourceDocument
from .utils import load_json, stable_json_hash, utc_now

AUTHORITY_LEVELS = {
    "primary": 1.0,
    "official": 0.95,
    "scholarly": 0.85,
    "reputable-secondary": 0.70,
    "community": 0.40,
    "unknown": 0.15,
}
DIRECTNESS_LEVELS = {
    "direct": 1.0,
    "derived": 0.65,
    "tertiary": 0.40,
    "unknown": 0.15,
}
SOURCE_ROLES = {
    "evidence",
    "context",
    "counterevidence",
    "verification_anchor",
    "evaluation_only",
}


class SourceQualityError(ValueError):
    """A source catalog cannot support a reproducible distillation."""


def _valid_locator(value: str) -> bool:
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        return bool(parsed.netloc)
    return bool(value.strip())


def _freshness_score(item: dict[str, Any]) -> float:
    scope = item.get("temporal_scope", "evergreen")
    if scope in {"historical", "evergreen"}:
        return 1.0
    published = item.get("published_at")
    if not isinstance(published, str) or not published:
        return 0.0
    try:
        date = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    age_days = max((datetime.now(timezone.utc) - date).days, 0)
    if age_days <= 365:
        return 1.0
    if age_days <= 730:
        return 0.6
    return 0.2


def assess_source(item: dict[str, Any], catalog_dir: Path) -> dict[str, Any]:
    required = {
        "id",
        "ingest",
        "uri",
        "title",
        "authority",
        "directness",
        "independence_group",
        "role",
        "coverage",
        "access",
    }
    missing = sorted(required - set(item))
    errors: list[str] = []
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    authority = item.get("authority", "unknown")
    directness = item.get("directness", "unknown")
    role = item.get("role", "evidence")
    if authority not in AUTHORITY_LEVELS:
        errors.append(f"invalid authority: {authority}")
    if directness not in DIRECTNESS_LEVELS:
        errors.append(f"invalid directness: {directness}")
    if role not in SOURCE_ROLES:
        errors.append(f"invalid role: {role}")
    coverage = item.get("coverage", [])
    if not isinstance(coverage, list) or any(not isinstance(value, str) for value in coverage):
        errors.append("coverage must be a string array")
        coverage = []
    ingest = item.get("ingest", "")
    resolved_ingest = ingest
    if isinstance(ingest, str) and not ingest.startswith(("http://", "https://")):
        path = Path(ingest).expanduser()
        if not path.is_absolute():
            path = catalog_dir / path
        resolved_ingest = str(path.resolve())
        if not path.is_file():
            errors.append(f"local ingest path does not exist: {resolved_ingest}")
    elif not isinstance(ingest, str) or not _valid_locator(ingest):
        errors.append("ingest must be a local file or public URL")
    uri = item.get("uri", "")
    if not isinstance(uri, str) or not _valid_locator(uri):
        errors.append("uri must be a stable source locator")
    accessible = item.get("accessible", True)
    if accessible is not True:
        errors.append("source is marked inaccessible")

    completeness = sum(
        bool(item.get(field))
        for field in (
            "title",
            "independence_group",
            "creator",
            "locator",
            "usage_rights",
        )
    ) / 5
    traceability = sum(
        (
            bool(item.get("uri")),
            bool(item.get("locator")),
            bool(item.get("independence_group")),
        )
    ) / 3
    rights = 1.0 if item.get("usage_rights") or item.get("license") else 0.25
    score = (
        0.30 * AUTHORITY_LEVELS.get(authority, 0.0)
        + 0.20 * DIRECTNESS_LEVELS.get(directness, 0.0)
        + 0.20 * traceability
        + 0.10 * rights
        + 0.10 * _freshness_score(item)
        + 0.10 * completeness
    )
    threshold = float(item.get("minimum_quality", 0.58))
    if authority == "unknown":
        errors.append("unknown authority cannot support a protected claim")
    if score < threshold:
        errors.append(f"quality score {score:.3f} is below {threshold:.3f}")
    return {
        **item,
        "ingest_input": ingest,
        "ingest": resolved_ingest,
        "coverage": coverage,
        "quality_score": round(score, 4),
        "eligible": not errors,
        "reasons": errors,
    }


def _default_requirements(profile: str, mode: str) -> dict[str, Any]:
    if mode == "quick":
        return {
            "minimum_independent_groups": 1,
            "minimum_primary_sources": 1,
            "required_roles": ["evidence"],
            "minimum_coverage": 1.0,
            "require_evaluation_holdout": False,
        }
    if mode == "deep":
        roles = ["evidence", "verification_anchor"]
        if profile in {"person", "hybrid"}:
            roles.append("counterevidence")
        return {
            "minimum_independent_groups": 3,
            "minimum_primary_sources": 2,
            "required_roles": roles,
            "minimum_coverage": 1.0,
            "require_evaluation_holdout": True,
        }
    return {
        "minimum_independent_groups": 2,
        "minimum_primary_sources": 1,
        "required_roles": ["evidence", "verification_anchor"],
        "minimum_coverage": 1.0,
        "require_evaluation_holdout": True,
    }


def audit_source_catalog(
    path: Path,
    profile: str = "content",
    mode: str = "standard",
) -> dict[str, Any]:
    catalog_path = path.expanduser().resolve()
    catalog = load_json(catalog_path)
    if catalog.get("schema_version") != "1.0":
        raise SourceQualityError("source catalog requires schema_version 1.0")
    sources = catalog.get("sources")
    questions = catalog.get("research_questions")
    if not isinstance(sources, list) or not sources:
        raise SourceQualityError("source catalog requires a non-empty sources array")
    if any(not isinstance(item, dict) for item in sources):
        raise SourceQualityError("source catalog entries must be objects")
    if not isinstance(questions, list) or not questions or any(
        not isinstance(value, str) or not value.strip() for value in questions
    ):
        raise SourceQualityError("source catalog requires research_questions")
    source_ids = [item.get("id") for item in sources if isinstance(item, dict)]
    if len(source_ids) != len(set(source_ids)):
        raise SourceQualityError("source catalog IDs must be unique")
    assessed = [assess_source(item, catalog_path.parent) for item in sources]
    selected = [
        item
        for item in assessed
        if item["eligible"] and item.get("role") != "evaluation_only"
    ]
    evaluation_only = [
        item for item in assessed if item["eligible"] and item.get("role") == "evaluation_only"
    ]
    requirements = {
        **_default_requirements(profile, mode),
        **catalog.get("requirements", {}),
    }
    groups = {item["independence_group"] for item in selected}
    primary = [item for item in selected if item["authority"] == "primary"]
    roles = {item["role"] for item in selected}
    covered = {
        question
        for item in selected
        for question in item["coverage"]
        if question in questions
    }
    coverage_rate = len(covered) / len(questions)
    gaps: list[str] = []
    if len(groups) < int(requirements["minimum_independent_groups"]):
        gaps.append(
            "independent source groups "
            f"{len(groups)} < {requirements['minimum_independent_groups']}"
        )
    if len(primary) < int(requirements["minimum_primary_sources"]):
        gaps.append(
            f"primary sources {len(primary)} < {requirements['minimum_primary_sources']}"
        )
    missing_roles = sorted(set(requirements["required_roles"]) - roles)
    if missing_roles:
        gaps.append(f"missing source roles: {', '.join(missing_roles)}")
    if coverage_rate < float(requirements["minimum_coverage"]):
        missing_questions = [question for question in questions if question not in covered]
        gaps.append(f"uncovered research questions: {', '.join(missing_questions)}")
    unknown_coverage = sorted(
        {
            question
            for item in assessed
            for question in item["coverage"]
            if question not in questions
        }
    )
    if unknown_coverage:
        gaps.append(
            f"source coverage references unknown questions: {', '.join(unknown_coverage)}"
        )
    if requirements.get("require_evaluation_holdout") and not evaluation_only:
        gaps.append("no evaluation_only source is reserved as a leakage barrier")
    return {
        "schema_version": "1.0",
        "catalog": str(catalog_path),
        "catalog_hash": stable_json_hash(catalog),
        "subject": catalog.get("subject", ""),
        "profile": profile,
        "mode": mode,
        "audited_at": utc_now(),
        "status": "passed" if not gaps else "blocked",
        "requirements": requirements,
        "research_questions": questions,
        "metrics": {
            "candidate_count": len(assessed),
            "selected_count": len(selected),
            "evaluation_only_count": len(evaluation_only),
            "independent_groups": len(groups),
            "primary_sources": len(primary),
            "coverage_rate": round(coverage_rate, 4),
            "mean_quality": round(
                sum(item["quality_score"] for item in selected) / len(selected), 4
            )
            if selected
            else 0.0,
        },
        "gaps": gaps,
        "selected_sources": selected,
        "evaluation_only_sources": evaluation_only,
        "excluded_sources": [item for item in assessed if not item["eligible"]],
    }


def apply_catalog_metadata(
    documents: list[SourceDocument],
    report: dict[str, Any],
) -> list[SourceDocument]:
    by_ingest: dict[str, dict[str, Any]] = {}
    for item in [
        *report.get("selected_sources", []),
        *report.get("evaluation_only_sources", []),
    ]:
        by_ingest[item["ingest"]] = item
        by_ingest[item["uri"]] = item
    enriched: list[SourceDocument] = []
    for document in documents:
        key = document.source
        if not key.startswith(("http://", "https://")):
            key = str(Path(key).expanduser().resolve())
        item = by_ingest.get(key)
        if not item:
            enriched.append(document)
            continue
        enriched.append(
            replace(
                document,
                authority=item["authority"],
                directness=item["directness"],
                independence_group=item["independence_group"],
                source_role=item["role"],
                source_uri=item["uri"],
                creator=item.get("creator"),
                published_at=item.get("published_at"),
                quality_score=float(item["quality_score"]),
                license=item.get("license") or document.license,
            )
        )
    return enriched


def source_quality_fingerprint(report: dict[str, Any]) -> str:
    """Hash semantic source decisions, excluding machine paths and timestamps."""

    def compact(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in (
                "id",
                "uri",
                "title",
                "authority",
                "directness",
                "independence_group",
                "role",
                "coverage",
                "published_at",
                "license",
                "usage_rights",
                "access",
                "quality_score",
                "eligible",
                "reasons",
            )
        }

    semantic = {
        "schema_version": report.get("schema_version"),
        "catalog_hash": report.get("catalog_hash"),
        "subject": report.get("subject"),
        "profile": report.get("profile"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "requirements": report.get("requirements"),
        "research_questions": report.get("research_questions"),
        "gaps": report.get("gaps"),
        "selected_sources": [
            compact(item) for item in report.get("selected_sources", [])
        ],
        "evaluation_only_sources": [
            compact(item) for item in report.get("evaluation_only_sources", [])
        ],
        "excluded_sources": [
            compact(item) for item in report.get("excluded_sources", [])
        ],
    }
    return stable_json_hash(semantic)


def write_source_catalog_template(path: Path) -> Path:
    template = {
        "schema_version": "1.0",
        "subject": "object being distilled",
        "research_questions": ["question-1", "question-2"],
        "requirements": {
            "minimum_independent_groups": 2,
            "minimum_primary_sources": 1,
            "required_roles": ["evidence", "verification_anchor"],
            "minimum_coverage": 1.0,
            "require_evaluation_holdout": True,
        },
        "sources": [
            {
                "id": "source-1",
                "ingest": "./captured/source-1.md",
                "uri": "https://example.org/original",
                "title": "Original source",
                "creator": "Author or institution",
                "authority": "primary",
                "directness": "direct",
                "independence_group": "publisher-or-archive",
                "role": "evidence",
                "coverage": ["question-1"],
                "temporal_scope": "evergreen",
                "published_at": "2026-01-01",
                "locator": "page, section, timestamp, or commit",
                "license": "unknown",
                "usage_rights": "link-and-short-quotes",
                "access": "public",
                "accessible": True,
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
