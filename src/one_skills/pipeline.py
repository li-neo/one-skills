"""Recoverable ten-phase distillation orchestration."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .compiler import capability_from_candidate, compile_skill
from .constants import CONSENT_LEVELS, MODES, OBJECT_TYPES, PHASE_INDEX, PHASES
from .database import KnowledgeDB
from .extraction import approve_candidate, extract_candidates, merge_candidates, verify_candidates
from .ingest import expand_sources, structural_chunks
from .models import Candidate, Capability, Evidence
from .profiles import PROFILES, detect_profile, profile_prompt
from .provider import ModelProvider, model_capability, verify_candidate
from .recipes import initialize_registry
from .retrieval import local_embedding
from .utils import append_jsonl, atomic_write, dump_json, load_json, new_id, slugify, utc_now


class PipelineError(RuntimeError):
    pass


def init_workspace(path: Path, mode: str = "standard") -> Path:
    if mode not in MODES:
        raise PipelineError(f"unsupported mode: {mode}")
    root = path.expanduser().resolve()
    for relative in ("packs", "dist", "knowledge/sources", "knowledge/normalized", ".one"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    dump_json(
        root / ".one" / "config.json",
        {
            "schema_version": "0.1",
            "default_mode": mode,
            "database": ".one/knowledge.db",
            "packs_dir": "packs",
            "dist_dir": "dist",
        },
    )
    with KnowledgeDB(root / ".one" / "knowledge.db"):
        pass
    initialize_registry(root / ".one" / "recipes.json")
    return root


def workspace_for(path: Path) -> Path:
    current = path.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".one" / "config.json").exists():
            return candidate
    raise PipelineError(f"no one-skills workspace found from {path}")


def _new_state(pack_id: str) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": "0.1",
        "pack_id": pack_id,
        "current_phase": "contract",
        "created_at": now,
        "updated_at": now,
        "phases": {
            phase: {
                "status": "in_progress" if phase == "contract" else "pending",
                "updated_at": now if phase == "contract" else None,
                "notes": "",
            }
            for phase in PHASES
        },
    }


def _state_markdown(state: dict[str, Any]) -> str:
    rows = [
        "# Pipeline State",
        "",
        f"当前阶段：`{state['current_phase']}`",
        "",
        "| 阶段 | 状态 | 更新时间 | 备注 |",
        "|---|---|---|---|",
    ]
    for phase in PHASES:
        item = state["phases"][phase]
        rows.append(
            f"| {phase} | {item['status']} | {item.get('updated_at') or ''} | "
            f"{item.get('notes') or ''} |"
        )
    rows.extend(["", "> `PIPELINE_STATE.json` 是机器状态真源；本文件仅供人工阅读。", ""])
    return "\n".join(rows)


def save_state(pack: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    dump_json(pack / "PIPELINE_STATE.json", state)
    atomic_write(pack / "PIPELINE_STATE.md", _state_markdown(state))


def load_state(pack: Path) -> dict[str, Any]:
    path = pack / "PIPELINE_STATE.json"
    if not path.exists():
        raise PipelineError(f"invalid pack; missing {path}")
    state = load_json(path)
    if state.get("current_phase") not in PHASES:
        raise PipelineError("pipeline current_phase is invalid")
    return state


def advance_phase(pack: Path, phase: str, status: str, notes: str = "") -> dict[str, Any]:
    if phase not in PHASES:
        raise PipelineError(f"unknown phase: {phase}")
    if status not in {"pending", "in_progress", "completed", "blocked"}:
        raise PipelineError(f"unknown phase status: {status}")
    state = load_state(pack)
    if status == "completed":
        unfinished = [
            previous
            for previous in PHASES[: PHASE_INDEX[phase]]
            if state["phases"][previous]["status"] != "completed"
        ]
        if unfinished:
            raise PipelineError(f"cannot skip unfinished phases: {', '.join(unfinished)}")
    state["phases"][phase] = {"status": status, "updated_at": utc_now(), "notes": notes}
    if status == "completed" and PHASE_INDEX[phase] < len(PHASES) - 1:
        next_phase = PHASES[PHASE_INDEX[phase] + 1]
        if state["phases"][next_phase]["status"] == "pending":
            state["phases"][next_phase] = {
                "status": "in_progress",
                "updated_at": utc_now(),
                "notes": "",
            }
        state["current_phase"] = next_phase
    else:
        state["current_phase"] = phase
    save_state(pack, state)
    return state


def _contract(
    name: str,
    profile: str,
    mode: str,
    sources: list[str],
    consent: str,
) -> str:
    source_list = "\n".join(f"- `{source}`" for source in sources)
    return f"""# Distillation Contract

- 对象：{name}
- Profile：`{profile}`
- 模式：`{mode}`
- 授权：`{consent}`
- 创建时间：{utc_now()}

## 来源

{source_list}

## 目标与成功标准

将来源中可验证、可迁移、可执行的能力编译为带证据、边界、测试和版本的 Agent Skills。

## 默认边界

- 不凭模型记忆补齐来源事实。
- 不扩大来源访问权限和工具执行权限。
- 模型推断必须显式标记，V2 预测力必须由独立模型或人工确认。
"""


def create_pack(
    workspace: Path,
    sources: list[str],
    requested_profile: str = "auto",
    mode: str = "standard",
    name: str | None = None,
    access_level: str = "private-local",
    consent: str | None = None,
) -> Path:
    if requested_profile not in OBJECT_TYPES:
        raise PipelineError(f"unsupported profile: {requested_profile}")
    if mode not in MODES:
        raise PipelineError(f"unsupported mode: {mode}")
    root = init_workspace(workspace, mode) if not (workspace / ".one").exists() else workspace.resolve()
    documents = expand_sources(sources, access_level)
    profile = detect_profile(documents, sources) if requested_profile == "auto" else requested_profile
    if profile not in PROFILES:
        raise PipelineError(f"profile has no implementation: {profile}")
    if profile == "person":
        if consent not in CONSENT_LEVELS:
            raise PipelineError(
                "person Profile requires --consent self, consented, work-authorized, or public-only"
            )
        if consent == "prohibited":
            raise PipelineError("person distillation is prohibited by the consent contract")
        if consent == "public-only" and access_level != "public":
            raise PipelineError("public-only consent requires --access public")
    resolved_name = name or documents[0].title
    pack = root / "packs" / slugify(resolved_name)
    if pack.exists() and any(pack.iterdir()):
        raise PipelineError(f"pack already exists and is not empty: {pack}")
    for relative in (
        "sources",
        "candidates",
        "verified",
        "rejected",
        "skills",
        "evolution/rounds",
        "audit",
    ):
        (pack / relative).mkdir(parents=True, exist_ok=True)
    pack_id = new_id("pack")
    save_state(pack, _new_state(pack_id))
    dump_json(
        pack / "pack.json",
        {
            "schema_version": "0.1",
            "id": pack_id,
            "name": resolved_name,
            "slug": pack.name,
            "profile": profile,
            "mode": mode,
            "sources": sources,
            "access_level": access_level,
            "consent": consent or "not-applicable",
            "created_at": utc_now(),
        },
    )
    atomic_write(pack / "EVIDENCE_LEDGER.jsonl", "")
    atomic_write(
        pack / "DISTILLATION_CONTRACT.md",
        _contract(resolved_name, profile, mode, sources, consent or "not-applicable"),
    )
    advance_phase(pack, "contract", "completed", "contract generated from explicit CLI inputs")
    _ingest_documents(root, pack, documents, profile)
    return pack


def _ingest_documents(
    workspace: Path,
    pack: Path,
    documents: list,
    profile: str,
    append: bool = False,
) -> None:
    database_path = workspace / ".one" / "knowledge.db"
    existing_manifest = load_json(pack / "SOURCE_MANIFEST.json")["sources"] if append else []
    existing_chunks = load_json(pack / "sources" / "chunks.json") if append else []
    manifest: list[dict[str, Any]] = list(existing_manifest)
    all_chunks: list[dict[str, Any]] = list(existing_chunks)
    with KnowledgeDB(database_path) as database:
        for document in documents:
            source_id, document_id, version, created = database.add_document(document, profile)
            if version > 1:
                for item in manifest:
                    if item.get("document_id") == document_id:
                        item["active"] = False
                all_chunks = [
                    item for item in all_chunks if item.get("document_id") != document_id
                ]
            normalized_path = workspace / "knowledge" / "normalized" / document_id / f"{version}.md"
            atomic_write(normalized_path, document.text + "\n")
            chunks = structural_chunks(document, document_id, version)
            database.add_chunks(chunks, {chunk.id: local_embedding(chunk.text) for chunk in chunks})
            manifest.append(
                {
                    **document.metadata(),
                    "source_id": source_id,
                    "document_id": document_id,
                    "document_version": version,
                    "created": created,
                    "active": True,
                    "normalized_uri": str(normalized_path),
                    "chunk_ids": [chunk.id for chunk in chunks],
                }
            )
            all_chunks.extend(asdict(chunk) for chunk in chunks)
    dump_json(pack / "SOURCE_MANIFEST.json", {"profile": profile, "sources": manifest})
    dump_json(pack / "sources" / "chunks.json", all_chunks)
    advance_phase(pack, "ingest", "completed", f"indexed {len(documents)} sources")
    _write_object_map(pack, profile, manifest)


def update_pack(pack: Path, sources: list[str]) -> dict[str, Any]:
    """Incrementally ingest changed sources and invalidate downstream phases."""
    metadata = load_json(pack / "pack.json")
    documents = expand_sources(sources, metadata["access_level"])
    before = load_json(pack / "SOURCE_MANIFEST.json")["sources"]
    state = load_state(pack)
    for phase in PHASES[PHASE_INDEX["ingest"] :]:
        state["phases"][phase] = {
            "status": "in_progress" if phase == "ingest" else "pending",
            "updated_at": utc_now() if phase == "ingest" else None,
            "notes": "invalidated by incremental source update",
        }
    state["current_phase"] = "ingest"
    save_state(pack, state)
    metadata["sources"] = list(dict.fromkeys([*metadata["sources"], *sources]))
    metadata["updated_at"] = utc_now()
    dump_json(pack / "pack.json", metadata)
    workspace = workspace_for(pack)
    _ingest_documents(workspace, pack, documents, metadata["profile"], append=True)
    after = load_json(pack / "SOURCE_MANIFEST.json")["sources"]
    changed = [item for item in after[len(before) :] if item["created"]]
    existing_skills = sorted(path.parent.name for path in (pack / "skills").glob("*/SKILL.md"))
    reports = pack / "reports"
    reports.mkdir(exist_ok=True)
    atomic_write(
        reports / "IMPACT.md",
        "# Incremental Impact\n\n"
        f"- New source versions: {len(changed)}\n"
        f"- Existing Skills requiring regression: {', '.join(existing_skills) or 'none'}\n"
        "- Downstream phases extract through evolve were invalidated and must pass again.\n",
    )
    return {
        "new_source_versions": len(changed),
        "affected_skills": existing_skills,
        "current_phase": load_state(pack)["current_phase"],
    }


def _write_object_map(pack: Path, profile: str, manifest: list[dict[str, Any]]) -> None:
    profile_definition = PROFILES[profile]
    source_rows = "\n".join(
        f"- {item['title']}：{item['character_count']} chars，sha256 `{item['content_hash']}`"
        for item in manifest
    )
    dimensions = "\n".join(f"- {dimension}: 待提取" for dimension in profile_definition.map_dimensions)
    atomic_write(
        pack / "OBJECT_MAP.md",
        f"""# Object Map

## Profile

`{profile}`，编译策略：`{profile_definition.compiler}`

## 来源

{source_rows}

## 地图维度

{dimensions}

## 抽取契约

```text
{profile_prompt(profile)}
```
""",
    )
    advance_phase(pack, "map", "completed", "profile map initialized")
    extract_pack(pack)


def _candidate_dict(candidate: Candidate) -> dict[str, Any]:
    return asdict(candidate)


def extract_pack(pack: Path) -> tuple[list[Candidate], list[Evidence]]:
    metadata = load_json(pack / "pack.json")
    chunk_values = load_json(pack / "sources" / "chunks.json")
    from .models import Chunk

    chunks = [Chunk(**value) for value in chunk_values]
    candidates, evidence = extract_candidates(
        chunks,
        metadata["profile"],
        {"quick": 6, "standard": 12, "deep": 24, "continuous": 12}[metadata["mode"]],
    )
    candidates = merge_candidates(candidates)
    dump_json(pack / "candidates" / "candidates.json", [_candidate_dict(item) for item in candidates])
    for item in evidence:
        append_jsonl(pack / "EVIDENCE_LEDGER.jsonl", item.to_dict())
    advance_phase(pack, "extract", "completed", f"extracted {len(candidates)} candidates")
    verified = verify_candidates(candidates, deep=metadata["mode"] == "deep")
    dump_json(pack / "verified" / "decisions.json", [_candidate_dict(item) for item in verified])
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


def approve_and_compile(pack: Path, candidate_id: str, reason: str) -> Path:
    decisions_path = pack / "verified" / "decisions.json"
    values = load_json(decisions_path)
    candidates = [Candidate(**value) for value in values]
    target = next((item for item in candidates if item.id == candidate_id), None)
    if not target:
        raise PipelineError(f"candidate not found: {candidate_id}")
    if target.status == "rejected" and not (target.cross_domain and target.actionable and target.distinctive):
        raise PipelineError("candidate failed deterministic gates and cannot be approved without re-extraction")
    approve_candidate(target, reason)
    dump_json(decisions_path, [_candidate_dict(item) for item in candidates])
    evidence = [
        json.loads(line)
        for line in (pack / "EVIDENCE_LEDGER.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    linked = [item for item in evidence if item.get("id") in target.evidence_ids]
    profile = load_json(pack / "pack.json")["profile"]
    capability = capability_from_candidate(target, profile)
    skill_dir = compile_skill(pack, capability, linked, profile=profile)
    workspace = workspace_for(pack)
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        database.add_capability(capability.id, capability.name, profile, capability.to_dict())
        for evidence_id in capability.evidence_ids:
            database.add_edge("evidence", evidence_id, "supports", "capability", capability.id)
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


def verify_and_compile_with_model(
    pack: Path,
    provider: ModelProvider,
    allow_sensitive_data: bool = False,
) -> list[Path]:
    """Run independent semantic gates and compile every accepted candidate."""
    metadata = load_json(pack / "pack.json")
    if metadata["access_level"] != "public" and not allow_sensitive_data:
        raise PipelineError(
            "non-public Pack data cannot be sent to a model without explicit "
            "--allow-sensitive-data authorization"
        )
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
            candidate.cross_domain = verification["cross_domain"]
            candidate.predictive = verification["predictive"]
            candidate.distinctive = verification["distinctive"]
            candidate.actionable = verification["actionable"]
            if not verification["accepted"]:
                candidate.status = "rejected"
                candidate.rejection_reason = verification["reason"]
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
                database.add_edge("evidence", evidence_id, "supports", "capability", capability.id)
    dump_json(decisions_path, [_candidate_dict(item) for item in candidates])
    dump_json(pack / "audit" / "model-verification.json", audit)
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
    }
    dump_json(pack / "ir" / "distillation.json", ir)
