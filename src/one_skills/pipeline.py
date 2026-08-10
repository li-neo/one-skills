"""Recoverable ten-phase distillation orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .compiler import capability_from_candidate, compile_skill
from .database import KnowledgeDB
from .errors import PipelineError
from .extraction import (
    approve_candidate,
    extract_candidates,
    extract_candidates_with_model,
    extract_structured_claims,
    merge_candidates,
    verify_candidates,
)
from .learning import build_learning_path
from .lifecycle import (
    advance_phase,
    init_workspace,
    load_state,
    save_state,
    workspace_for,
)
from .models import Candidate, Capability, Evidence
from .portfolio import build_portfolio
from .profiles import PROFILES, profile_prompt
from .provider import (
    ModelProvider,
    model_capability,
    verify_candidate,
    verify_candidate_with_roles,
)
from .source_workflow import (
    create_pack,
    lineage,
    revoke_source,
    select_regression_tests,
    update_pack,
)
from .utils import (
    append_jsonl,
    atomic_write,
    dump_json,
    load_json,
    utc_now,
)

__all__ = [
    "PipelineError",
    "advance_phase",
    "approve_and_compile",
    "compile_confirmed_portfolio",
    "create_pack",
    "extract_pack",
    "init_workspace",
    "lineage",
    "load_state",
    "reextract_with_model",
    "revoke_source",
    "save_state",
    "select_regression_tests",
    "update_pack",
    "verify_and_compile_with_model",
    "verify_pack_with_roles",
    "workspace_for",
]


def _candidate_dict(candidate: Candidate) -> dict[str, Any]:
    return asdict(candidate)


def extract_pack(pack: Path) -> tuple[list[Candidate], list[Evidence]]:
    metadata = load_json(pack / "pack.json")
    chunk_values = load_json(pack / "sources" / "chunks.json")
    from .models import Chunk

    chunks = [Chunk(**value) for value in chunk_values]
    structured_candidates, structured_evidence = extract_structured_claims(
        chunks,
        metadata["profile"],
    )
    heuristic_candidates, heuristic_evidence = extract_candidates(
        chunks,
        metadata["profile"],
        {"quick": 6, "standard": 12, "deep": 24, "continuous": 12}[metadata["mode"]],
    )
    candidates = merge_candidates([*structured_candidates, *heuristic_candidates])
    evidence = [*structured_evidence, *heuristic_evidence]
    dump_json(pack / "candidates" / "candidates.json", [_candidate_dict(item) for item in candidates])
    build_portfolio(pack, candidates, kind="candidate")
    for item in evidence:
        append_jsonl(pack / "EVIDENCE_LEDGER.jsonl", item.to_dict())
    _index_evidence(pack, evidence)
    advance_phase(pack, "extract", "completed", f"extracted {len(candidates)} candidates")
    verified = verify_candidates(
        candidates,
        deep=metadata["mode"] == "deep",
        require_independent_sources=metadata["profile"] in {"person", "hybrid"},
    )
    dump_json(pack / "verified" / "decisions.json", [_candidate_dict(item) for item in verified])
    build_portfolio(pack, verified, kind="verified")
    for item in verified:
        if item.status == "rejected":
            dump_json(pack / "rejected" / f"{item.id}.json", _candidate_dict(item))
    advance_phase(
        pack,
        "verify",
        "blocked",
        "V2 predictive-power judgments require model or human approval",
    )
    return verified, evidence


def reextract_with_model(
    pack: Path,
    provider: ModelProvider,
    allow_sensitive_data: bool = False,
    workers: int = 5,
) -> tuple[list[Candidate], list[Evidence]]:
    metadata = load_json(pack / "pack.json")
    if metadata["access_level"] != "public" and not allow_sensitive_data:
        raise PipelineError(
            "non-public Pack data cannot be sent to a model without explicit authorization"
        )
    from .models import Chunk

    chunks = [Chunk(**value) for value in load_json(pack / "sources" / "chunks.json")]
    overview = (
        load_json(pack / "OBJECT_OVERVIEW.json")
        if (pack / "OBJECT_OVERVIEW.json").exists()
        else {}
    )
    candidates, evidence = extract_candidates_with_model(
        provider,
        chunks,
        metadata["profile"],
        workers,
        overview,
    )
    dump_json(pack / "candidates" / "semantic-candidates.json", [_candidate_dict(item) for item in candidates])
    build_portfolio(pack, candidates, kind="candidate")
    for item in evidence:
        append_jsonl(pack / "EVIDENCE_LEDGER.jsonl", item.to_dict())
    _index_evidence(pack, evidence)
    verified = verify_candidates(
        candidates,
        deep=True,
        require_independent_sources=metadata["profile"] in {"person", "hybrid"},
    )
    dump_json(pack / "verified" / "decisions.json", [_candidate_dict(item) for item in verified])
    build_portfolio(pack, verified, kind="verified")
    definition = PROFILES[metadata["profile"]]
    view_count = len(
        definition.spec.extractor_views
        if definition.spec
        else definition.candidate_kinds
    )
    state = load_state(pack)
    state["phases"]["extract"] = {
        "status": "completed",
        "updated_at": utc_now(),
        "notes": f"{view_count} semantic views",
    }
    state["phases"]["verify"] = {
        "status": "blocked",
        "updated_at": utc_now(),
        "notes": "semantic candidates require independent verification",
    }
    state["current_phase"] = "verify"
    save_state(pack, state)
    return verified, evidence


def _index_evidence(pack: Path, evidence: list[Evidence]) -> None:
    workspace = workspace_for(pack)
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        for item in evidence:
            if item.chunk_id:
                chunk_rows = database.rows(
                    "SELECT id FROM chunks WHERE id = ? AND document_id = ? "
                    "AND document_version = ?",
                    (item.chunk_id, item.source, item.document_version),
                )
            else:
                chunk_rows = database.rows(
                    "SELECT c.id FROM chunks c "
                    "JOIN documents d ON d.id = c.document_id "
                    "WHERE c.document_id = ? AND c.source_locator = ? "
                    "AND c.document_version = d.active_version",
                    (item.source, item.locator),
                )
            if not chunk_rows:
                raise PipelineError(
                    f"evidence {item.id} does not resolve to an active source chunk"
                )
            database.add_claim(
                item.claim,
                item.confidence,
                [row["id"] for row in chunk_rows],
                claim_id=item.id,
            )


def approve_and_compile(pack: Path, candidate_id: str, reason: str) -> Path:
    decisions_path = pack / "verified" / "decisions.json"
    values = load_json(decisions_path)
    candidates = [Candidate(**value) for value in values]
    target = next((item for item in candidates if item.id == candidate_id), None)
    if not target:
        raise PipelineError(f"candidate not found: {candidate_id}")
    profile = load_json(pack / "pack.json")["profile"]
    source_gate = target.source_independent or profile not in {"person", "hybrid"}
    if target.status == "rejected" and not (
        target.cross_domain
        and source_gate
        and target.actionable
        and target.distinctive
    ):
        raise PipelineError("candidate failed deterministic gates and cannot be approved without re-extraction")
    approve_candidate(target, reason)
    dump_json(decisions_path, [_candidate_dict(item) for item in candidates])
    evidence = [
        json.loads(line)
        for line in (pack / "EVIDENCE_LEDGER.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    linked = [item for item in evidence if item.get("id") in target.evidence_ids]
    capability = capability_from_candidate(target, profile)
    skill_dir = compile_skill(pack, capability, linked, profile=profile)
    workspace = workspace_for(pack)
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        database.add_capability(capability.id, capability.name, profile, capability.to_dict())
        for evidence_id in capability.evidence_ids:
            database.add_edge("claim", evidence_id, "supports", "capability", capability.id)
        database.add_edge("capability", capability.id, "produces", "skill", skill_dir.name)
    state = load_state(pack)
    state["phases"]["verify"] = {
        "status": "completed",
        "updated_at": utc_now(),
        "notes": f"candidate {candidate_id} approved: {reason}",
    }
    state["current_phase"] = "compile"
    state["phases"]["compile"] = {"status": "in_progress", "updated_at": utc_now(), "notes": ""}
    save_state(pack, state)
    advance_phase(pack, "compile", "completed", f"compiled {skill_dir.name}")
    _build_index(pack)
    return skill_dir


def verify_pack_with_roles(
    pack: Path,
    roles: Any,
    allow_sensitive_data: bool = False,
    semantic_extract: bool = True,
) -> dict[str, Any]:
    """Verify a v0.3 portfolio without compiling before human confirmation."""
    metadata = load_json(pack / "pack.json")
    if (
        metadata.get("semantic_contract", {}).get("overview_confirmation")
        != "confirmed"
    ):
        raise PipelineError("confirm Object Overview before model verification")
    if metadata["access_level"] != "public" and not allow_sensitive_data:
        raise PipelineError(
            "non-public Pack data cannot be sent to model roles without explicit "
            "--allow-sensitive-data authorization"
        )
    providers = roles.providers()
    if semantic_extract:
        reextract_with_model(
            pack,
            providers["builder"],
            allow_sensitive_data,
        )
    decisions_path = pack / "verified" / "decisions.json"
    candidates = [Candidate(**value) for value in load_json(decisions_path)]
    evidence = [
        json.loads(line)
        for line in (pack / "EVIDENCE_LEDGER.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    contract = profile_prompt(metadata["profile"])
    audit: list[dict[str, Any]] = []
    accepted = 0
    for candidate in candidates:
        if candidate.status == "rejected" and not candidate.cross_domain:
            audit.append(
                {
                    "candidate_id": candidate.id,
                    "accepted": False,
                    "reason": candidate.rejection_reason,
                    "stage": "deterministic-v1",
                }
            )
            continue
        related = [
            item for item in evidence if item.get("id") in candidate.evidence_ids
        ]
        verification = verify_candidate_with_roles(
            providers["answer"],
            providers["judge"],
            asdict(candidate),
            related or evidence[:50],
            contract,
        )
        candidate.cross_domain = (
            verification["cross_domain"]
            and len(set(candidate.source_contexts)) >= 2
        )
        candidate.source_independent = len(set(candidate.independence_groups)) >= 2
        candidate.predictive = verification["predictive"]
        candidate.distinctive = verification["distinctive"]
        candidate.actionable = verification["actionable"]
        source_gate = (
            candidate.source_independent
            or metadata["profile"] not in {"person", "hybrid"}
        )
        if verification["accepted"] and candidate.cross_domain and source_gate:
            generated = model_capability(
                providers["builder"],
                asdict(candidate),
                related,
                contract,
            )
            candidate.problem = generated["problem"]
            candidate.triggers = [generated["trigger"]]
            candidate.inputs = generated["inputs"]
            candidate.procedure = generated["procedure"]
            candidate.output = generated["output"]
            candidate.done = generated["done"]
            candidate.boundaries = generated["boundaries"]
            candidate.failures = generated["failures"]
            candidate.status = "accepted"
            candidate.rejection_reason = ""
            candidate.verification = {
                **verification,
                "fallback": generated["fallback"],
                "generated_name": generated["name"],
                "isolation_level": roles.isolation_level,
            }
            accepted += 1
        else:
            candidate.status = "rejected"
            candidate.rejection_reason = (
                verification["reason"]
                if source_gate
                else "selected Profile requires two independent provenance groups"
            )
            candidate.verification = {
                **verification,
                "isolation_level": roles.isolation_level,
            }
            dump_json(
                pack / "rejected" / f"{candidate.id}.json",
                _candidate_dict(candidate),
            )
        audit.append(
            {
                "candidate_id": candidate.id,
                "isolation_level": roles.isolation_level,
                **verification,
            }
        )
    dump_json(decisions_path, [_candidate_dict(item) for item in candidates])
    dump_json(
        pack / "audit" / "model-verification.json",
        {
            "generated_at": utc_now(),
            "isolation_level": roles.isolation_level,
            "records": audit,
        },
    )
    portfolio = build_portfolio(pack, candidates, kind="verified")
    advance_phase(
        pack,
        "verify",
        "blocked",
        (
            f"{accepted} candidates passed role-separated V1/V2/V3; "
            "confirm VERIFIED_PORTFOLIO before compile"
        ),
    )
    return {
        "accepted": accepted,
        "rejected": len(candidates) - accepted,
        "portfolio": str(pack / "VERIFIED_PORTFOLIO.json"),
        "portfolio_status": portfolio["status"],
        "isolation_level": roles.isolation_level,
    }


def compile_confirmed_portfolio(pack: Path) -> dict[str, Any]:
    """Compile a confirmed v0.3 portfolio through its Profile-specific compiler."""
    metadata = load_json(pack / "pack.json")
    semantic = metadata.get("semantic_contract", {})
    if semantic.get("overview_confirmation") != "confirmed":
        raise PipelineError("Object Overview is not confirmed")
    if semantic.get("capability_confirmation") != "confirmed":
        raise PipelineError("Verified Capability Portfolio is not confirmed")
    from .compiler import compile_verified_portfolio

    advance_phase(
        pack,
        "verify",
        "completed",
        "role-separated V1/V2/V3 and human portfolio confirmation passed",
    )
    skill_dir, capabilities = compile_verified_portfolio(pack)
    advance_phase(
        pack,
        "compile",
        "completed",
        f"compiled {len(capabilities)} internal modules behind {skill_dir.name}",
    )
    _write_distillation_ir(pack, [skill_dir])
    advance_phase(
        pack,
        "link",
        "completed",
        "capability graph, index, glossary, digest, and learning path projected",
    )
    return {
        "skill": str(skill_dir),
        "modules": len(capabilities),
        "current_phase": load_state(pack)["current_phase"],
    }


def verify_and_compile_with_model(
    pack: Path,
    provider: ModelProvider,
    allow_sensitive_data: bool = False,
    semantic_extract: bool = True,
) -> list[Path]:
    """Run independent semantic gates and compile every accepted candidate."""
    metadata = load_json(pack / "pack.json")
    if metadata["access_level"] != "public" and not allow_sensitive_data:
        raise PipelineError(
            "non-public Pack data cannot be sent to a model without explicit "
            "--allow-sensitive-data authorization"
        )
    if semantic_extract and not (pack / "candidates" / "semantic-candidates.json").exists():
        reextract_with_model(pack, provider, allow_sensitive_data)
    decisions_path = pack / "verified" / "decisions.json"
    candidates = [Candidate(**value) for value in load_json(decisions_path)]
    evidence = [
        json.loads(line)
        for line in (pack / "EVIDENCE_LEDGER.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    contract = profile_prompt(metadata["profile"])
    audit: list[dict[str, Any]] = []
    compiled: list[Path] = []
    workspace = workspace_for(pack)
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        for candidate in candidates:
            related = [item for item in evidence if item.get("id") in candidate.evidence_ids]
            # The independent verifier also sees nearby evidence so it can test recurrence.
            verification = verify_candidate(provider, asdict(candidate), evidence[:50], contract)
            audit.append({"candidate_id": candidate.id, **verification})
            candidate.cross_domain = (
                verification["cross_domain"]
                and len(set(candidate.source_contexts)) >= 2
            )
            candidate.source_independent = len(
                set(candidate.independence_groups)
            ) >= 2
            candidate.predictive = verification["predictive"]
            candidate.distinctive = verification["distinctive"]
            candidate.actionable = verification["actionable"]
            source_gate = (
                candidate.source_independent
                or metadata["profile"] not in {"person", "hybrid"}
            )
            if not verification["accepted"] or not candidate.cross_domain or not source_gate:
                candidate.status = "rejected"
                candidate.rejection_reason = (
                    verification["reason"]
                    if source_gate
                    else "person and hybrid Profiles require two independent provenance groups"
                )
                dump_json(pack / "rejected" / f"{candidate.id}.json", _candidate_dict(candidate))
                continue
            candidate.status = "accepted"
            candidate.rejection_reason = ""
            generated = model_capability(provider, asdict(candidate), related, contract)
            capability = Capability(
                **generated,
                evidence_ids=list(candidate.evidence_ids),
                confidence=0.85,
            )
            skill_dir = compile_skill(pack, capability, related, profile=metadata["profile"])
            compiled.append(skill_dir)
            database.add_capability(
                capability.id,
                capability.name,
                metadata["profile"],
                capability.to_dict(),
            )
            for evidence_id in capability.evidence_ids:
                database.add_edge("claim", evidence_id, "supports", "capability", capability.id)
            database.add_edge("capability", capability.id, "produces", "skill", skill_dir.name)
    dump_json(decisions_path, [_candidate_dict(item) for item in candidates])
    dump_json(pack / "audit" / "model-verification.json", audit)
    build_portfolio(pack, candidates, kind="verified")
    if not compiled:
        advance_phase(pack, "verify", "blocked", "independent model accepted no candidates")
        return []
    state = load_state(pack)
    state["phases"]["verify"] = {
        "status": "completed",
        "updated_at": utc_now(),
        "notes": f"independent model accepted {len(compiled)} candidates",
    }
    state["current_phase"] = "compile"
    state["phases"]["compile"] = {"status": "in_progress", "updated_at": utc_now(), "notes": ""}
    save_state(pack, state)
    advance_phase(pack, "compile", "completed", f"compiled {len(compiled)} Skills")
    _build_index(pack)
    return compiled


def _build_index(pack: Path) -> None:
    skills = sorted(path.parent for path in (pack / "skills").glob("*/SKILL.md"))
    rows = "\n".join(f"- [{skill.name}](skills/{skill.name}/SKILL.md)" for skill in skills)
    atomic_write(
        pack / "INDEX.md",
        f"# Skill Graph\n\n## Skills\n\n{rows or '- none'}\n\n"
        "## Relations\n\nNo relation is emitted without explicit evidence.\n",
    )
    _write_distillation_ir(pack, skills)
    build_learning_path(pack)
    advance_phase(pack, "link", "completed", f"linked {len(skills)} skills")


def _write_distillation_ir(pack: Path, skills: list[Path]) -> None:
    metadata = load_json(pack / "pack.json")
    manifest = load_json(pack / "SOURCE_MANIFEST.json")
    evidence = [
        json.loads(line)
        for line in (pack / "EVIDENCE_LEDGER.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    capabilities = [load_json(skill / "capability.json") for skill in skills]
    evals = [
        test
        for skill in skills
        for test in load_json(skill / "test-prompts.json")
    ]
    ir = {
        "schema_version": "1.0",
        "object": {
            "id": metadata["id"],
            "type": metadata["profile"],
            "goal": "compile evidence-linked, executable Agent Skills",
            "scope": f"{len(manifest['sources'])} captured source versions",
            "consent": metadata["consent"],
        },
        "sources": manifest["sources"],
        "claims": [
            {
                "id": item["id"],
                "statement": item["claim"],
                "status": "cited",
                "confidence": item["confidence"],
                "evidence": [item["locator"]],
            }
            for item in evidence
        ],
        "capabilities": capabilities,
        "style": {
            "enabled": metadata["profile"] == "person",
            "mode": "advisor",
            "forbidden_patterns": ["identity impersonation", "unsupported sensitive inference"],
        },
        "evals": evals,
        "learning_path": load_json(pack / "LEARNING_PATH.json"),
        "object_overview": (
            load_json(pack / "OBJECT_OVERVIEW.json")
            if (pack / "OBJECT_OVERVIEW.json").exists()
            else {}
        ),
        "capability_portfolio": (
            load_json(pack / "VERIFIED_PORTFOLIO.json")
            if (pack / "VERIFIED_PORTFOLIO.json").exists()
            else {}
        ),
        "capability_graph": (
            load_json(pack / "CAPABILITY_GRAPH.json")
            if (pack / "CAPABILITY_GRAPH.json").exists()
            else {}
        ),
        "evaluation_runs": [],
    }
    dump_json(pack / "ir" / "distillation.json", ir)
