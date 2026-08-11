"""Candidate consolidation, disposition, and human-review portfolios."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .core_assets import (
    load_reproducibility,
    load_source_quality,
    update_pack_metadata,
)
from .models import Candidate
from .retrieval import tokenize
from .utils import atomic_write, dump_json, load_json, stable_json_hash, utc_now


class PortfolioError(ValueError):
    pass


def enrich_candidate(candidate: Candidate) -> Candidate:
    """Fill executable fields conservatively without claiming model judgments."""
    if not candidate.problem:
        candidate.problem = f"在相关场景中判断何时以及如何应用“{candidate.title}”"
    if not candidate.assumptions:
        candidate.assumptions = ["来源语境与当前问题具有可解释的结构对应"]
    if not candidate.mechanism:
        candidate.mechanism = [candidate.summary]
    if not candidate.triggers:
        candidate.triggers = [f"用户明确需要处理与“{candidate.title}”对应的问题"]
    if not candidate.anti_triggers:
        candidate.anti_triggers = ["纯信息查询", "关键事实或成立假设缺失"]
    if not candidate.inputs:
        candidate.inputs = ["用户目标", "当前约束", "可验证事实"]
    if not candidate.procedure:
        candidate.procedure = [
            "确认目标、成立假设和关键事实",
            "按证据运行候选机制并保留备选解释",
            "定义完成、改判、停止和降级条件",
        ]
    if not candidate.output:
        candidate.output = "带证据、边界和改判条件的可执行结果"
    if not candidate.done:
        candidate.done = "结果可由来源和后续行动复核"
    if not candidate.boundaries:
        candidate.boundaries = ["不得把来源未支持的推断写成事实"]
    if not candidate.failures:
        candidate.failures = ["证据不足", "成立假设不满足"]
    if candidate.candidate_type in {"case", "applications"}:
        candidate.disposition = "case"
    elif candidate.candidate_type in {"counterexample", "failures"}:
        candidate.disposition = "counterexample"
    elif candidate.candidate_type in {"term", "glossary"}:
        candidate.disposition = "term"
    return candidate


def _overlap(left: Candidate, right: Candidate) -> float:
    left_terms = set(tokenize(f"{left.title} {left.summary}"))
    right_terms = set(tokenize(f"{right.title} {right.summary}"))
    union = left_terms | right_terms
    return len(left_terms & right_terms) / len(union) if union else 0.0


def portfolio_metrics(candidates: list[Candidate]) -> dict[str, Any]:
    pairs = [
        _overlap(left, right)
        for index, left in enumerate(candidates)
        for right in candidates[index + 1 :]
    ]
    high_overlap = sum(value >= 0.65 for value in pairs)
    independent = [
        item
        for item in candidates
        if item.disposition == "independent-module" and item.status != "rejected"
    ]
    weak_modules = sum(
        len(item.evidence_ids) < 2 or len(item.source_contexts) < 2
        for item in independent
    )
    return {
        "candidate_count": len(candidates),
        "accepted_count": sum(item.status == "accepted" for item in candidates),
        "overlap_rate": round(high_overlap / len(pairs), 4) if pairs else 0.0,
        "fragmentation_rate": (
            round(weak_modules / len(independent), 4) if independent else 0.0
        ),
    }


def _coverage(pack: Path, candidates: list[Candidate]) -> dict[str, list[str]]:
    questions = load_source_quality(pack).get("research_questions", [])
    coverage: dict[str, list[str]] = {question: [] for question in questions}
    for question in questions:
        question_terms = set(tokenize(question))
        for candidate in candidates:
            candidate_terms = set(
                tokenize(
                    " ".join(
                        [
                            candidate.title,
                            candidate.summary,
                            *candidate.tags,
                        ]
                    )
                )
            )
            if question_terms & candidate_terms:
                coverage[question].append(candidate.id)
    return coverage


def _render_candidate(candidate: Candidate) -> list[str]:
    return [
        f"### {candidate.title}",
        "",
        f"- ID: `{candidate.id}`",
        f"- Type / disposition: `{candidate.candidate_type}` / `{candidate.disposition}`",
        f"- Status: `{candidate.status}`",
        f"- Summary: {candidate.summary}",
        f"- Context recurrence: {len(set(candidate.source_contexts))}",
        f"- Independent groups: {len(set(candidate.independence_groups))}",
        f"- Evidence: {', '.join(f'`{value}`' for value in candidate.evidence_ids)}",
        f"- Rejection / pending reason: {candidate.rejection_reason or 'none'}",
        "",
    ]


def render_portfolio(value: dict[str, Any], candidates: list[Candidate]) -> str:
    by_id = {item.id: item for item in candidates}
    lines = [
        f"# {'Verified ' if value['kind'] == 'verified' else ''}Capability Portfolio",
        "",
        f"- Profile: `{value['profile']}`",
        f"- Status: `{value['status']}`",
        f"- Candidates: {value['metrics']['candidate_count']}",
        f"- Accepted: {value['metrics']['accepted_count']}",
        f"- Overlap rate: {value['metrics']['overlap_rate']:.1%}",
        f"- Fragmentation rate: {value['metrics']['fragmentation_rate']:.1%}",
        "",
    ]
    for title, key in (
        ("Independent modules", "accepted"),
        ("Degraded units", "degraded"),
        ("Merged units", "merged"),
        ("Rejected units", "rejected"),
    ):
        lines.extend([f"## {title}", ""])
        items = value[key]
        if not items:
            lines.append("- none")
            lines.append("")
            continue
        for item in items:
            candidate_id = item if isinstance(item, str) else item.get("id")
            candidate = by_id.get(candidate_id)
            if candidate:
                lines.extend(_render_candidate(candidate))
            else:
                lines.append(f"- `{candidate_id}`: {item}")
        lines.append("")
    lines.extend(
        [
            "## Research question coverage",
            "",
            "| Question | Candidate IDs |",
            "|---|---|",
        ]
    )
    for question, ids in value["coverage"].items():
        lines.append(f"| {question} | {', '.join(f'`{item}`' for item in ids) or 'gap'} |")
    lines.extend(
        [
            "",
            "> Portfolio confirmation approves the ability selection, not release or task effectiveness.",
            "",
        ]
    )
    return "\n".join(lines)


def build_portfolio(
    pack: Path,
    candidates: list[Candidate],
    *,
    kind: str,
) -> dict[str, Any]:
    if kind not in {"candidate", "verified"}:
        raise PortfolioError(f"unknown portfolio kind: {kind}")
    enriched = [enrich_candidate(item) for item in candidates]
    accepted = [
        item.id
        for item in enriched
        if item.disposition == "independent-module"
        and item.status in {"accepted", "needs_model_verification", "needs_evidence"}
    ]
    degraded = [
        {"id": item.id, "disposition": item.disposition}
        for item in enriched
        if item.disposition != "independent-module" and item.status != "rejected"
    ]
    rejected = [
        {"id": item.id, "reason": item.rejection_reason}
        for item in enriched
        if item.status == "rejected"
    ]
    metadata = load_json(pack / "pack.json")
    value = {
        "schema_version": "1.0",
        "pack_id": metadata["id"],
        "profile": metadata["profile"],
        "kind": kind,
        "status": "candidate",
        "accepted": accepted,
        "degraded": degraded,
        "merged": [],
        "rejected": rejected,
        "coverage": _coverage(pack, enriched),
        "metrics": portfolio_metrics(enriched),
        "confirmed_at": None,
        "confirmation_notes": "",
        "generated_at": utc_now(),
        "candidates": [asdict(item) for item in enriched],
    }
    stem = "VERIFIED_PORTFOLIO" if kind == "verified" else "CANDIDATE_PORTFOLIO"
    dump_json(pack / f"{stem}.json", value)
    atomic_write(pack / f"{stem}.md", render_portfolio(value, enriched))
    if kind == "verified":
        portfolio_hash = stable_json_hash(value)
        constraints = load_reproducibility(pack)
        constraints["capability_portfolio_hash"] = portfolio_hash

        def update_metadata(current: dict[str, Any]) -> None:
            current["capability_portfolio_hash"] = portfolio_hash
            current.setdefault("semantic_contract", {})[
                "capability_confirmation"
            ] = "pending"
            current["reproducibility"] = constraints

        update_pack_metadata(pack, update_metadata)
    return value


def confirm_portfolio(pack: Path, notes: str) -> dict[str, Any]:
    if not notes.strip():
        raise PortfolioError("Capability Portfolio confirmation requires notes")
    path = pack / "VERIFIED_PORTFOLIO.json"
    if not path.exists():
        raise PortfolioError("Verified Capability Portfolio does not exist")
    value = load_json(path)
    if not value.get("accepted"):
        raise PortfolioError("Capability Portfolio has no accepted or pending modules")
    value["status"] = "confirmed"
    value["confirmed_at"] = utc_now()
    value["confirmation_notes"] = notes.strip()
    dump_json(path, value)
    candidates = [Candidate(**item) for item in value["candidates"]]
    atomic_write(pack / "VERIFIED_PORTFOLIO.md", render_portfolio(value, candidates))
    portfolio_hash = stable_json_hash(value)
    constraints = load_reproducibility(pack)
    constraints["capability_portfolio_hash"] = portfolio_hash

    def update_metadata(metadata: dict[str, Any]) -> None:
        metadata["capability_portfolio_hash"] = portfolio_hash
        metadata.setdefault("semantic_contract", {})[
            "capability_confirmation"
        ] = "confirmed"
        metadata["reproducibility"] = constraints

    update_pack_metadata(pack, update_metadata)
    return value


def apply_reviewed_capability_spec(
    pack: Path,
    spec_path: Path,
    verification_path: Path,
    *,
    isolation_level: str,
    minimum_modules: int = 1,
) -> dict[str, Any]:
    """Bind Builder specifications to independently reviewed candidate records."""
    values = [
        Candidate(**item)
        for item in load_json(pack / "verified" / "decisions.json")
    ]
    by_title = {item.title: item for item in values}
    spec_value = load_json(spec_path)
    modules = spec_value.get("modules")
    if not isinstance(modules, list):
        raise PortfolioError("capability specification requires modules array")
    review_artifact = load_json(verification_path)
    if isinstance(review_artifact, dict):
        expected_source_hash = stable_json_hash(
            load_reproducibility(pack).get(
                "source_hashes",
                {},
            )
        )
        artifact_source_hash = review_artifact.get("source_set_hash")
        if artifact_source_hash and artifact_source_hash != expected_source_hash:
            raise PortfolioError(
                "candidate verification belongs to a different Source Set"
            )
        reviews = review_artifact.get("records")
    else:
        reviews = review_artifact
    if not isinstance(reviews, list):
        raise PortfolioError("verification import requires a JSON array")
    review_by_id = {
        item.get("candidate_id"): item
        for item in reviews
        if isinstance(item, dict)
    }
    review_by_title = {
        item.get("claim_key"): item
        for item in reviews
        if isinstance(item, dict) and item.get("claim_key")
    }
    selected_titles = {
        item.get("claim_key")
        for item in modules
        if isinstance(item, dict)
    }
    original_ids: dict[str, str] = {}
    for claim_key in selected_titles:
        candidate = by_title.get(claim_key)
        if candidate is None:
            raise PortfolioError(
                f"capability specification has unknown Claim-Key: {claim_key}"
            )
        original_ids[str(claim_key)] = candidate.id
        candidate.id = str(claim_key)
    title_to_id = {
        title: candidate.id
        for title, candidate in by_title.items()
    }
    accepted = 0
    deployable = 0
    for module in modules:
        if not isinstance(module, dict):
            raise PortfolioError("capability module specifications must be objects")
        claim_key = module.get("claim_key")
        candidate = by_title.get(claim_key)
        if candidate is None:
            raise PortfolioError(f"capability specification has unknown Claim-Key: {claim_key}")
        review = review_by_id.get(original_ids[claim_key]) or review_by_title.get(
            claim_key
        )
        if not review:
            raise PortfolioError(f"candidate has no independent review: {claim_key}")
        boolean_fields = (
            "cross_domain",
            "predictive",
            "distinctive",
            "actionable",
            "boundary",
        )
        if any(not isinstance(review.get(field), bool) for field in boolean_fields):
            raise PortfolioError(f"candidate review is incomplete: {claim_key}")
        accepted_review = all(review[field] for field in boolean_fields)
        supporting_review = all(
            review[field]
            for field in (
                "cross_domain",
                "predictive",
                "actionable",
                "boundary",
            )
        )
        module_role = str(module.get("module_role") or "capability")
        candidate.cross_domain = (
            review["cross_domain"]
            and len(set(candidate.source_contexts)) >= 2
        )
        candidate.source_independent = len(set(candidate.independence_groups)) >= 2
        candidate.predictive = review["predictive"]
        candidate.distinctive = review["distinctive"]
        candidate.actionable = review["actionable"]
        candidate.problem = str(module.get("problem") or candidate.summary)
        candidate.assumptions = list(module.get("assumptions") or [])
        candidate.mechanism = list(module.get("mechanism") or [])
        candidate.triggers = list(module.get("triggers") or [])
        candidate.anti_triggers = list(module.get("anti_triggers") or [])
        candidate.inputs = list(module.get("inputs") or [])
        candidate.procedure = list(module.get("procedure") or [])
        candidate.branches = list(module.get("branches") or [])
        candidate.output = str(module.get("output") or "")
        candidate.done = str(module.get("done") or "")
        candidate.boundaries = list(module.get("boundaries") or [])
        candidate.failures = list(module.get("failures") or [])
        candidate.counterexamples = list(module.get("counterexamples") or [])
        candidate.related_ids = [
            {
                "relation": relation["relation"],
                "target": title_to_id.get(
                    relation.get("target"),
                    relation.get("target", ""),
                ),
            }
            for relation in module.get("relations", [])
            if isinstance(relation, dict)
            and relation.get("relation")
            and relation.get("target")
        ]
        candidate.verification = {
            **review,
            "generated_name": str(module.get("name") or claim_key),
            "fallback": str(module.get("fallback") or "停止并补充证据"),
            "isolation_level": isolation_level,
        }
        if accepted_review and candidate.cross_domain:
            candidate.status = "accepted"
            candidate.disposition = "independent-module"
            candidate.rejection_reason = ""
            accepted += 1
            deployable += 1
        elif module_role == "governance" and review["boundary"] and review["actionable"]:
            candidate.status = "needs_evidence"
            candidate.disposition = "governance"
            candidate.rejection_reason = (
                "retained as a governance gate; predictive power is not its contract"
            )
            deployable += 1
        elif supporting_review and candidate.cross_domain:
            candidate.status = "needs_evidence"
            candidate.disposition = "shared-principle"
            candidate.rejection_reason = (
                "V3 distinctiveness failed; retained as an internal supporting principle"
            )
            deployable += 1
        else:
            candidate.status = "rejected"
            candidate.disposition = "rejected"
            candidate.rejection_reason = str(
                review.get("reason") or "independent review failed"
            )
    for candidate in values:
        if candidate.title not in selected_titles and candidate.status != "rejected":
            candidate.status = "rejected"
            candidate.disposition = "rejected"
            candidate.rejection_reason = (
                "not selected by the confirmed capability specification"
            )
    if deployable < minimum_modules:
        raise PortfolioError(
            f"reviewed internal modules {deployable} < required {minimum_modules}"
        )
    dump_json(
        pack / "verified" / "decisions.json",
        [asdict(item) for item in values],
    )
    dump_json(
        pack / "audit" / "role-separated-verification.json",
        {
            "schema_version": "1.0",
            "isolation_level": isolation_level,
            "spec": str(spec_path),
            "verification": str(verification_path),
            "accepted": accepted,
            "deployable": deployable,
            "records": reviews,
            "imported_at": utc_now(),
        },
    )
    return build_portfolio(pack, values, kind="verified")
