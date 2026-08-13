"""Application commands for Pack creation, source updates, and revocation."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Any

from .constants import CONSENT_LEVELS, MODES, PHASE_INDEX, PHASES
from .core_assets import (
    CONSOLIDATED_PACK_VERSION,
    load_reproducibility,
    load_source_manifest,
    load_source_quality,
    save_reproducibility,
    save_source_manifest,
    update_pack_metadata,
)
from .database import KnowledgeDB
from .errors import PipelineError
from .evaluation_state import mark_evaluations_stale
from .ingest import expand_sources, structural_chunks
from .learning import build_learning_path
from .lifecycle import (
    advance_phase,
    init_workspace,
    load_state,
    new_lifecycle,
    save_state,
    workspace_for,
)
from .locking import file_lock, pack_lock, workspace_pack_lock_path
from .overview import build_object_overview
from .profiles import PROFILES, detect_profile, load_profile_plugins
from .provenance import source_set_fingerprint
from .recipes import initialize_registry
from .retrieval import local_embedding
from .source_quality import (
    apply_catalog_metadata,
    audit_source_catalog,
    source_quality_fingerprint,
)
from .storage import LocalBlobStore
from .utils import (
    append_jsonl,
    atomic_write,
    dump_json,
    iter_jsonl,
    load_json,
    new_id,
    slugify,
    utc_now,
)

_DB_WRITE_LOCK = Lock()


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


def _portable_workspace_path(value: str, workspace: Path) -> str:
    if value.startswith(("http://", "https://")):
        return value
    prefix = ""
    raw = value
    if value.startswith("file://"):
        prefix = "file:"
        raw = value[7:]
    fragment = ""
    if "#" in raw:
        raw, fragment = raw.split("#", 1)
        fragment = "#" + fragment
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (workspace / path).resolve()
    try:
        relative = path.resolve().relative_to(workspace.resolve())
    except ValueError:
        return value
    return prefix + relative.as_posix() + fragment


def _portable_source_quality(
    report: dict[str, Any],
    workspace: Path,
) -> dict[str, Any]:
    portable = json.loads(json.dumps(report))
    if portable.get("catalog"):
        portable["catalog"] = _portable_workspace_path(
            portable["catalog"],
            workspace,
        )
    for key in (
        "selected_sources",
        "evaluation_only_sources",
        "excluded_sources",
    ):
        for item in portable.get(key, []):
            original = item.pop("ingest_input", item.get("ingest", ""))
            item["ingest"] = (
                original
                if original
                and not original.startswith(("http://", "https://"))
                and not Path(original).expanduser().is_absolute()
                else _portable_workspace_path(original, workspace)
            )
    return portable


def create_pack(
    workspace: Path,
    sources: list[str],
    requested_profile: str = "auto",
    mode: str = "standard",
    name: str | None = None,
    access_level: str = "private-local",
    consent: str | None = None,
    source_catalog: Path | None = None,
    activation_aliases: list[str] | None = None,
) -> Path:
    load_profile_plugins()
    if requested_profile != "auto" and requested_profile not in PROFILES:
        raise PipelineError(f"unsupported profile: {requested_profile}")
    if mode not in MODES:
        raise PipelineError(f"unsupported mode: {mode}")
    root = (
        init_workspace(workspace, mode)
        if not (workspace / ".one").exists()
        else workspace.resolve()
    )
    source_quality = None
    resolved_sources = list(sources)
    if source_catalog is not None:
        profile_hint = requested_profile if requested_profile != "auto" else "content"
        source_quality = audit_source_catalog(source_catalog, profile_hint, mode)
        if source_quality["status"] != "passed":
            raise PipelineError(
                "source quality gate blocked distillation: "
                + "; ".join(source_quality["gaps"])
            )
        resolved_sources.extend(
            item["ingest"] for item in source_quality["selected_sources"]
        )
    resolved_sources = list(dict.fromkeys(resolved_sources))
    if not resolved_sources:
        raise PipelineError("distillation requires --source or --source-catalog")
    documents = expand_sources(resolved_sources, access_level)
    profile = (
        detect_profile(documents, resolved_sources)
        if requested_profile == "auto"
        else requested_profile
    )
    if source_quality is not None and profile != source_quality["profile"]:
        source_quality = audit_source_catalog(source_catalog, profile, mode)
        if source_quality["status"] != "passed":
            raise PipelineError(
                "source quality gate blocked final Profile: "
                + "; ".join(source_quality["gaps"])
            )
    if source_quality is not None:
        documents = apply_catalog_metadata(documents, source_quality)
    if profile not in PROFILES:
        raise PipelineError(f"profile has no implementation: {profile}")
    registry_path = root / ".one" / "recipes.json"
    with file_lock(root / ".one" / "locks" / "recipes.lock"):
        initialize_registry(registry_path)
        recipe = load_json(registry_path)["active"].get(profile)
    if not recipe:
        raise PipelineError(f"profile has no active Recipe: {profile}")
    if profile == "person":
        if consent not in CONSENT_LEVELS:
            raise PipelineError(
                "person Profile requires --consent self, consented, "
                "work-authorized, or public-only"
            )
        if consent == "prohibited":
            raise PipelineError(
                "person distillation is prohibited by the consent contract"
            )
        if consent == "public-only" and access_level != "public":
            raise PipelineError("public-only consent requires --access public")
    resolved_name = name or documents[0].title
    stored_sources = (
        [
            *sources,
            *(item["uri"] for item in source_quality["selected_sources"]),
        ]
        if source_quality is not None
        else resolved_sources
    )
    stored_sources = list(
        dict.fromkeys(
            _portable_workspace_path(value, root)
            for value in stored_sources
        )
    )
    stored_quality = (
        _portable_source_quality(source_quality, root)
        if source_quality is not None
        else None
    )
    final_pack = root / "packs" / slugify(resolved_name)
    with file_lock(workspace_pack_lock_path(root, final_pack.name)):
        return _build_staged_pack(
            root,
            final_pack,
            resolved_name,
            profile,
            documents,
            mode,
            stored_sources,
            source_catalog,
            access_level,
            consent,
            recipe,
            stored_quality,
            activation_aliases,
        )


def _build_staged_pack(
    root: Path,
    final_pack: Path,
    resolved_name: str,
    profile: str,
    documents: list,
    mode: str,
    stored_sources: list[str],
    source_catalog: Path | None,
    access_level: str,
    consent: str | None,
    recipe: dict[str, Any],
    stored_quality: dict[str, Any] | None,
    activation_aliases: list[str] | None,
) -> Path:
    if final_pack.exists() and any(final_pack.iterdir()):
        raise PipelineError(f"pack already exists and is not empty: {final_pack}")
    if final_pack.exists():
        final_pack.rmdir()
    staging_root = root / ".one" / "staging" / "packs"
    staging_root.mkdir(parents=True, exist_ok=True)
    pack = staging_root / f"{final_pack.name}-{new_id('staging')}"
    try:
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
        _initialize_pack(
            root,
            pack,
            final_pack.name,
            resolved_name,
            profile,
            documents,
            mode,
            stored_sources,
            source_catalog,
            access_level,
            consent,
            recipe,
            stored_quality,
            activation_aliases,
        )
        os.replace(pack, final_pack)
        return final_pack
    except Exception:
        shutil.rmtree(pack, ignore_errors=True)
        raise


def _initialize_pack(
    root: Path,
    pack: Path,
    slug: str,
    resolved_name: str,
    profile: str,
    documents: list,
    mode: str,
    stored_sources: list[str],
    source_catalog: Path | None,
    access_level: str,
    consent: str | None,
    recipe: dict[str, Any],
    stored_quality: dict[str, Any] | None,
    activation_aliases: list[str] | None,
) -> None:
    pack_id = new_id("pack")
    recipe_lock = {
        "schema_version": "1.0",
        "locked_at": utc_now(),
        "recipe": recipe,
    }
    default_quality = stored_quality or {
        "schema_version": "1.0",
        "status": "unassessed",
        "audited_at": utc_now(),
        "gaps": [
            "no source catalog was supplied; provenance quality was not gated"
        ],
        "selected_sources": [],
        "evaluation_only_sources": [],
        "excluded_sources": [],
    }
    constraints = {
        "schema_version": "1.0",
        "created_at": utc_now(),
        "source_hashes": {},
        "source_quality_hash": source_quality_fingerprint(default_quality),
        "protected": [
            "source_facts",
            "authorization",
            "safety_boundaries",
            "negative_tests",
            "canonical_evals",
        ],
        "canonical_eval_hashes": {},
        "runtime_eval_hashes": {},
        "evaluation_suite_hashes": {},
        "skill_hashes": {},
    }
    dump_json(
        pack / "pack.json",
        {
            "schema_version": CONSOLIDATED_PACK_VERSION,
            "revision": 1,
            "id": pack_id,
            "name": resolved_name,
            "slug": slug,
            "profile": profile,
            "mode": mode,
            "sources": stored_sources,
            "source_catalog": (
                _portable_workspace_path(str(source_catalog.resolve()), root)
                if source_catalog
                else None
            ),
            "access_level": access_level,
            "consent": consent or "not-applicable",
            "recipe": {"id": recipe["id"], "version": recipe["version"]},
            "recipe_lock": recipe_lock,
            "reproducibility": constraints,
            "lifecycle": new_lifecycle(pack_id),
            "object_overview_hash": None,
            "capability_portfolio_hash": None,
            "capability_graph_hash": None,
            "semantic_contract": {
                "overview_confirmation": "pending",
                "capability_confirmation": "pending",
            },
            "activation_aliases": list(dict.fromkeys(activation_aliases or [])),
            "created_at": utc_now(),
        },
    )
    atomic_write(pack / "EVIDENCE_LEDGER.jsonl", "")
    atomic_write(
        pack / "INDEX.md",
        "# Skill Graph\n\n"
        "No compiled capabilities yet. This index is rebuilt after the compile phase.\n",
    )
    atomic_write(
        pack / "DISTILLATION_CONTRACT.md",
        _contract(
            resolved_name,
            profile,
            mode,
            stored_sources,
            consent or "not-applicable",
        ),
    )
    advance_phase(
        pack,
        "contract",
        "completed",
        "contract generated from explicit CLI inputs",
    )
    _ingest_documents(root, pack, documents, profile, quality=default_quality)


def _ingest_documents(
    workspace: Path,
    pack: Path,
    documents: list,
    profile: str,
    append: bool = False,
    quality: dict[str, Any] | None = None,
) -> None:
    database_path = workspace / ".one" / "knowledge.db"
    source_bundle = load_source_manifest(pack) if append else {}
    existing_manifest = source_bundle.get("sources", [])
    existing_chunks = (
        load_json(pack / "sources" / "chunks.json") if append else []
    )
    source_quality = (
        source_bundle.get("quality")
        if isinstance(source_bundle.get("quality"), dict)
        else quality or {}
    )
    manifest: list[dict[str, Any]] = list(existing_manifest)
    all_chunks: list[dict[str, Any]] = list(existing_chunks)
    blob_store = LocalBlobStore(workspace / "knowledge" / "sources")
    with _DB_WRITE_LOCK, KnowledgeDB(database_path) as database:
        for document in documents:
            raw_uri = blob_store.put_source(document)

            def normalized_uri(
                document_id: str,
                version: int,
                source_document=document,
            ) -> str:
                normalized_path = (
                    workspace
                    / "knowledge"
                    / "normalized"
                    / document_id
                    / f"{version}.md"
                )
                atomic_write(normalized_path, source_document.text + "\n")
                return _portable_workspace_path(
                    str(normalized_path),
                    workspace,
                )

            source_id, document_id, version, created, chunks = (
                database.ingest_document(
                    document,
                    profile,
                    lambda current_id, current_version, source_document=document: structural_chunks(
                        source_document,
                        current_id,
                        current_version,
                    ),
                    lambda values: {
                        chunk.id: local_embedding(chunk.text)
                        for chunk in values
                    },
                    normalized_uri,
                )
            )
            if not created and any(
                item.get("source_id") == source_id
                and item.get("document_version") == version
                for item in manifest
            ):
                continue
            if version > 1:
                for item in manifest:
                    if item.get("document_id") == document_id:
                        item["active"] = False
                all_chunks = [
                    item
                    for item in all_chunks
                    if item.get("document_id") != document_id
                ]
            normalized_path = (
                workspace / "knowledge" / "normalized" / document_id / f"{version}.md"
            )
            document_metadata = document.metadata()
            if document.source_uri:
                document_metadata["source"] = document.source_uri
            manifest.append(
                {
                    **document_metadata,
                    "source_id": source_id,
                    "document_id": document_id,
                    "document_version": version,
                    "created": created,
                    "active": True,
                    "normalized_uri": _portable_workspace_path(
                        str(normalized_path),
                        workspace,
                    ),
                    "raw_uri": _portable_workspace_path(raw_uri, workspace),
                    "chunk_ids": [chunk.id for chunk in chunks],
                }
            )
            all_chunks.extend(asdict(chunk) for chunk in chunks)
        database.invalidate_claims_from_inactive_versions()
    save_source_manifest(
        pack,
        profile=profile,
        sources=manifest,
        quality=source_quality,
    )
    dump_json(pack / "sources" / "chunks.json", all_chunks)
    constraints = load_reproducibility(pack)
    constraints["source_hashes"] = {
        f"{item['source_id']}@{item['document_version']}": item["content_hash"]
        for item in manifest
    }
    constraints["source_set_hash"] = source_set_fingerprint(
        {
            "sources": manifest,
        }
    )
    save_reproducibility(pack, constraints)
    advance_phase(pack, "ingest", "completed", f"indexed {len(documents)} sources")
    build_learning_path(pack)
    _map_and_extract(pack)


def _map_and_extract(pack: Path) -> None:
    build_object_overview(pack)
    advance_phase(pack, "map", "completed", "profile map initialized")
    from .pipeline import extract_pack

    extract_pack(pack)


def _reset_extraction_artifacts(pack: Path) -> None:
    history = pack / "audit" / "history" / new_id("source-update")
    history.mkdir(parents=True, exist_ok=True)
    for relative in (
        "EVIDENCE_LEDGER.jsonl",
        "candidates",
        "verified",
        "rejected",
    ):
        source = pack / relative
        if not source.exists():
            continue
        destination = history / relative
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    ledger = pack / "EVIDENCE_LEDGER.jsonl"
    preserved: list[str] = []
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if not item.get("chunk_id"):
                preserved.append(json.dumps(item, ensure_ascii=False))
    atomic_write(ledger, "\n".join(preserved) + ("\n" if preserved else ""))
    for relative in ("candidates", "verified", "rejected"):
        directory = pack / relative
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.glob("*.json"):
            path.unlink()


def update_pack(pack: Path, sources: list[str]) -> dict[str, Any]:
    """Incrementally ingest changed sources and invalidate downstream phases."""
    with pack_lock(pack):
        return _update_pack_locked(pack, sources)


def _update_pack_locked(pack: Path, sources: list[str]) -> dict[str, Any]:
    metadata = load_json(pack / "pack.json")
    workspace = workspace_for(pack)
    documents = expand_sources(sources, metadata["access_level"])
    quality = load_source_quality(pack)
    if metadata.get("source_catalog") and quality:
        catalog_path = Path(metadata["source_catalog"]).expanduser()
        if not catalog_path.is_absolute():
            catalog_path = workspace / catalog_path
        runtime_quality = audit_source_catalog(
            catalog_path,
            metadata["profile"],
            metadata["mode"],
        )
        if runtime_quality["status"] != "passed":
            raise PipelineError(
                "updated source catalog no longer passes: "
                + "; ".join(runtime_quality["gaps"])
            )
        constraints = load_reproducibility(pack)
        if constraints.get("source_quality_hash") != source_quality_fingerprint(
            runtime_quality
        ):
            raise PipelineError(
                "source catalog decisions changed; create a new Pack or explicitly "
                "re-freeze source quality before updating"
            )
        documents = apply_catalog_metadata(documents, runtime_quality)
    before = load_source_manifest(pack)["sources"]
    state = load_state(pack)
    for phase in PHASES[PHASE_INDEX["ingest"] :]:
        state["phases"][phase] = {
            "status": "in_progress" if phase == "ingest" else "pending",
            "updated_at": utc_now() if phase == "ingest" else None,
            "notes": "invalidated by incremental source update",
        }
    state["current_phase"] = "ingest"
    save_state(pack, state)

    def update_sources(current: dict[str, Any]) -> None:
        current["sources"] = list(
            dict.fromkeys(
                [
                    *current["sources"],
                    *(
                        _portable_workspace_path(source, workspace)
                        for source in sources
                    ),
                ]
            )
        )
        current["updated_at"] = utc_now()

    metadata = update_pack_metadata(pack, update_sources)
    mark_evaluations_stale(pack, "source set changed")
    _reset_extraction_artifacts(pack)
    _ingest_documents(
        workspace,
        pack,
        documents,
        metadata["profile"],
        append=True,
    )
    after = load_source_manifest(pack)["sources"]
    changed = [item for item in after[len(before) :] if item["created"]]
    existing_skills = sorted(
        path.parent.name for path in (pack / "skills").glob("*/SKILL.md")
    )
    reports = pack / "reports"
    reports.mkdir(exist_ok=True)
    atomic_write(
        reports / "IMPACT.md",
        "# Incremental Impact\n\n"
        f"- New source versions: {len(changed)}\n"
        f"- Existing Skills requiring regression: "
        f"{', '.join(existing_skills) or 'none'}\n"
        "- Downstream phases extract through evolve were invalidated and must pass again.\n",
    )
    return {
        "new_source_versions": len(changed),
        "affected_skills": existing_skills,
        "current_phase": load_state(pack)["current_phase"],
    }


def lineage(workspace: Path, node_type: str, node_id: str) -> list[dict[str, str]]:
    root = workspace_for(workspace)
    with KnowledgeDB(root / ".one" / "knowledge.db") as database:
        return database.descendants(node_type, node_id)


def revoke_source(workspace: Path, source_id: str, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise PipelineError("source revocation requires a reason")
    root = workspace_for(workspace)
    intent_directory = root / ".one" / "revocations"
    intent_directory.mkdir(parents=True, exist_ok=True)
    pending: list[dict[str, Any]] = []
    for path in sorted(intent_directory.glob("*.json")):
        candidate = load_json(path)
        if (
            candidate.get("status") == "pending"
            and candidate.get("source_id") == source_id
        ):
            pending.append(candidate)
    manifests: list[tuple[Path, list[dict[str, Any]]]] = []
    for manifest_path in (root / "packs").glob("*/SOURCE_MANIFEST.json"):
        manifest = load_json(manifest_path)
        matches = [
            item
            for item in manifest["sources"]
            if item["source_id"] == source_id
        ]
        if matches:
            manifests.append((manifest_path, matches))
    intent = (
        pending[0]
        if pending
        else {
            "schema_version": "1.0",
            "id": new_id("revocation"),
            "source_id": source_id,
            "reason": reason.strip(),
            "status": "pending",
            "affected_packs": [path.parent.name for path, _ in manifests],
            "created_at": utc_now(),
            "attempts": 0,
        }
    )
    intent_path = intent_directory / f"{intent['id']}.json"
    intent["attempts"] = int(intent.get("attempts", 0)) + 1
    intent["last_attempt_at"] = utc_now()
    dump_json(intent_path, intent)
    try:
        with KnowledgeDB(root / ".one" / "knowledge.db") as database:
            result = database.revoke_source(source_id)
        affected_skills = sorted(
            {
                edge["to_id"]
                for edge in result["affected"]
                if edge["to_type"] == "skill"
            }
        )
        for manifest_path, _ in manifests:
            pack = manifest_path.parent
            with pack_lock(pack):
                manifest = load_json(manifest_path)
                matches = [
                    item
                    for item in manifest["sources"]
                    if item["source_id"] == source_id
                ]
                revoked_chunks = {
                    chunk_id
                    for item in matches
                    for chunk_id in item.get("chunk_ids", [])
                }
                for item in matches:
                    item["active"] = False
                    item["revoked_at"] = utc_now()
                    item["revocation_reason"] = reason.strip()
                    item["revocation_intent_id"] = intent["id"]
                dump_json(manifest_path, manifest)
                constraints = load_reproducibility(pack)
                constraints["source_set_hash"] = source_set_fingerprint(
                    manifest
                )
                save_reproducibility(pack, constraints)
                mark_evaluations_stale(
                    pack,
                    f"source revoked: {source_id}",
                )
                _invalidate_revoked_evidence(pack, revoked_chunks, intent["id"])
                state = load_state(pack)
                for phase in PHASES[PHASE_INDEX["ingest"] :]:
                    state["phases"][phase] = {
                        "status": "blocked" if phase == "ingest" else "pending",
                        "updated_at": utc_now() if phase == "ingest" else None,
                        "notes": (
                            f"source revoked: {source_id}"
                            if phase == "ingest"
                            else ""
                        ),
                    }
                state["current_phase"] = "ingest"
                save_state(pack, state)
                log = pack / "audit" / "DELETION_LOG.md"
                previous = (
                    log.read_text(encoding="utf-8")
                    if log.exists()
                    else "# Deletion Log\n\n"
                )
                if intent["id"] not in previous:
                    atomic_write(
                        log,
                        previous
                        + f"- {utc_now()} intent `{intent['id']}` revoked "
                        f"`{source_id}`; reason: {reason.strip()}; affected Skills: "
                        f"{', '.join(affected_skills) or 'none'}\n",
                    )
                (pack / "reports").mkdir(exist_ok=True)
                regression = select_regression_tests(pack, affected_skills)
                dump_json(pack / "reports" / "regression-plan.json", regression)
        event = {
            "intent_id": intent["id"],
            "source_id": source_id,
            "reason": reason.strip(),
            "revoked_at": utc_now(),
            "affected_packs": intent["affected_packs"],
            "affected_skills": affected_skills,
        }
        event_log = root / ".one" / "revocations.jsonl"
        if not any(
            item.get("intent_id") == intent["id"]
            for item in iter_jsonl(event_log)
        ):
            append_jsonl(event_log, event)
        intent["status"] = "completed"
        intent["completed_at"] = utc_now()
        intent.pop("last_error", None)
        dump_json(intent_path, intent)
        return event
    except Exception as exc:
        intent["status"] = "pending"
        intent["last_error"] = f"{type(exc).__name__}: {exc}"
        dump_json(intent_path, intent)
        raise


def _invalidate_revoked_evidence(
    pack: Path,
    revoked_chunk_ids: set[str],
    intent_id: str,
) -> None:
    if not revoked_chunk_ids:
        return
    ledger = pack / "EVIDENCE_LEDGER.jsonl"
    if not ledger.exists():
        return
    kept: list[str] = []
    removed: list[str] = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        target = removed if item.get("chunk_id") in revoked_chunk_ids else kept
        target.append(json.dumps(item, ensure_ascii=False))
    if removed:
        history = pack / "audit" / "history" / intent_id
        history.mkdir(parents=True, exist_ok=True)
        atomic_write(history / "EVIDENCE_LEDGER.revoked.jsonl", "\n".join(removed) + "\n")
        atomic_write(ledger, "\n".join(kept) + ("\n" if kept else ""))


def select_regression_tests(
    pack: Path,
    affected_skills: list[str],
) -> dict[str, Any]:
    tests: list[dict[str, Any]] = []
    for skill_name in affected_skills:
        path = pack / "skills" / skill_name / "evals" / "canonical.json"
        if not path.exists():
            continue
        suite = load_json(path)
        tests.extend(
            {"skill": skill_name, **case}
            for case in suite["cases"]
        )
    for path in sorted((pack / "skills").glob("*/evals/canonical.json")):
        skill_name = path.parents[1].name
        if skill_name in affected_skills:
            continue
        suite = load_json(path)
        tests.extend(
            {"skill": skill_name, **case}
            for case in suite["cases"]
            if case["type"] in {"should_not_trigger", "sibling_bait", "safety"}
        )
    return {
        "generated_at": utc_now(),
        "affected_skills": affected_skills,
        "tests": tests,
        "count": len(tests),
    }
