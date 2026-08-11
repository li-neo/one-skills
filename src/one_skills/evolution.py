"""Structured, reversible whole-folder Skill evolution patches."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

from .evaluation_state import mark_evaluations_stale
from .experience import load_experiences
from .schema_runtime import require_schema
from .utils import dump_json, load_json, new_id, stable_json_hash, utc_now


class EvolutionError(ValueError):
    pass


VALID_ACTIONS = {"CREATE", "UPDATE", "MERGE", "PRUNE", "NOOP"}
PROTECTED_PARTS = {"evals", "test-prompts.json"}
PATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _save_patch(path: Path, patch: dict[str, Any]) -> None:
    require_schema(
        patch,
        "evolution-patch.schema.json",
        str(path),
    )
    dump_json(path, patch)


def skill_folder_hash(pack: Path) -> str:
    values = {}
    for path in sorted((pack / "skills").rglob("*")):
        if path.is_file():
            values[str(path.relative_to(pack))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return stable_json_hash(values)


def _safe_target(pack: Path, target: str) -> Path:
    root = (pack / "skills").resolve()
    path = (pack / target).resolve()
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise EvolutionError("evolution target must stay inside Pack skills") from exc
    if any(part in PROTECTED_PARTS for part in relative.parts):
        raise EvolutionError("canonical and runtime evaluations are frozen")
    return path


def _event_ids(pack: Path) -> set[str]:
    return {
        item["id"]
        for item in load_experiences(pack)
        if item.get("scope") == "training"
    }


def propose_patch(
    pack: Path,
    action: str,
    target: str,
    content: str,
    supporting_event_ids: list[str],
    expected_dimension: str,
    source_targets: list[str] | None = None,
) -> dict[str, Any]:
    action = action.upper()
    if action not in VALID_ACTIONS:
        raise EvolutionError(f"unsupported evolution action: {action}")
    if len(set(supporting_event_ids)) < 2:
        raise EvolutionError("evolution patch requires two independent training events")
    unknown = set(supporting_event_ids) - _event_ids(pack)
    if unknown:
        raise EvolutionError(
            "evolution patch references unknown or evaluation events: "
            + ", ".join(sorted(unknown))
        )
    target_path = _safe_target(pack, target)
    sources = [
        str(_safe_target(pack, value).relative_to(pack.resolve()))
        for value in (source_targets or [])
    ]
    if action == "CREATE" and target_path.exists():
        raise EvolutionError("CREATE target already exists")
    if action in {"UPDATE", "PRUNE"} and not target_path.is_file():
        raise EvolutionError(f"{action} target must be an existing file")
    if action == "MERGE" and len(sources) < 2:
        raise EvolutionError("MERGE requires at least two source targets")
    patch = {
        "schema_version": "1.0",
        "id": new_id("evolution-patch"),
        "action": action,
        "target": str(target_path.relative_to(pack.resolve())),
        "content": content,
        "source_targets": sources,
        "supporting_event_ids": list(dict.fromkeys(supporting_event_ids)),
        "expected_dimension": expected_dimension,
        "protected_gates": [
            "source_facts",
            "authorization",
            "safety",
            "canonical_evals",
            "negative_tests",
        ],
        "before_hash": skill_folder_hash(pack),
        "after_hash": None,
        "comparison": None,
        "status": "proposed",
        "decision_reason": "",
        "proposed_at": utc_now(),
    }
    directory = pack / "evolution" / "proposals"
    directory.mkdir(parents=True, exist_ok=True)
    _save_patch(directory / f"{patch['id']}.json", patch)
    return patch


def _validated_patch_id(value: object) -> str:
    if not isinstance(value, str) or not PATCH_ID_PATTERN.fullmatch(value):
        raise EvolutionError("evolution patch id is invalid")
    if value in {".", ".."}:
        raise EvolutionError("evolution patch id is invalid")
    return value


def _snapshot(pack: Path, patch: dict[str, Any], patch_id: str) -> Path:
    snapshot_root = (pack / "evolution" / "snapshots").resolve()
    root = (snapshot_root / _validated_patch_id(patch_id)).resolve()
    try:
        root.relative_to(snapshot_root)
    except ValueError as exc:
        raise EvolutionError("snapshot path must stay inside the Pack") from exc
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    paths = [patch["target"], *patch.get("source_targets", [])]
    manifest = {}
    for value in paths:
        path = pack / value
        if path.is_file():
            destination = root / value
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            manifest[value] = "file"
        else:
            manifest[value] = "missing"
    dump_json(root / "manifest.json", manifest)
    return root


def _apply(pack: Path, patch: dict[str, Any]) -> None:
    action = patch["action"]
    target = _safe_target(pack, patch["target"])
    if action == "NOOP":
        return
    if action in {"CREATE", "UPDATE"}:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(patch.get("content", ""), encoding="utf-8")
        return
    if action == "PRUNE":
        target.unlink()
        return
    if action == "MERGE":
        sections = [
            (pack / value).read_text(encoding="utf-8").strip()
            for value in patch["source_targets"]
        ]
        if patch.get("content", "").strip():
            sections.append(patch["content"].strip())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
        for value in patch["source_targets"]:
            source = pack / value
            if source.resolve() != target.resolve():
                source.unlink()


def apply_patch_candidate(
    pack: Path,
    patch_id: str,
    comparison: dict[str, Any],
) -> dict[str, Any]:
    path = pack / "evolution" / "proposals" / f"{patch_id}.json"
    patch = load_json(path)
    safe_patch_id = _validated_patch_id(patch_id)
    if patch.get("id") != safe_patch_id:
        raise EvolutionError("evolution patch id does not match its proposal filename")
    if patch["status"] != "proposed":
        raise EvolutionError("only proposed patches can be applied")
    required = {"before_score", "after_score", "hard_gates"}
    if not required <= set(comparison):
        raise EvolutionError("comparison requires before_score, after_score, and hard_gates")
    before_score = float(comparison["before_score"])
    after_score = float(comparison["after_score"])
    if not math.isfinite(before_score) or not math.isfinite(after_score):
        raise EvolutionError("comparison scores must be finite")
    hard_gates = comparison["hard_gates"]
    expected_gates = set(patch.get("protected_gates", []))
    if (
        not isinstance(hard_gates, dict)
        or set(hard_gates) != expected_gates
        or any(type(value) is not bool for value in hard_gates.values())
    ):
        raise EvolutionError("comparison hard_gates must exactly match protected_gates")
    if after_score <= before_score or not all(hard_gates.values()):
        patch["status"] = "rejected"
        patch["comparison"] = comparison
        patch["decision_reason"] = "candidate did not improve or failed a protected gate"
        _save_patch(path, patch)
        return patch
    if patch["before_hash"] != skill_folder_hash(pack):
        raise EvolutionError("Skill folder changed after patch proposal")
    _snapshot(pack, patch, safe_patch_id)
    _apply(pack, patch)
    patch["after_hash"] = skill_folder_hash(pack)
    patch["comparison"] = comparison
    patch["status"] = "applied"
    patch["applied_at"] = utc_now()
    _save_patch(path, patch)
    mark_evaluations_stale(pack, f"Skill changed by evolution patch {safe_patch_id}")
    return patch


def _restore(pack: Path, patch: dict[str, Any]) -> None:
    snapshot = pack / "evolution" / "snapshots" / patch["id"]
    manifest = load_json(snapshot / "manifest.json")
    for value, status in manifest.items():
        target = pack / value
        if status == "missing":
            if target.exists():
                target.unlink()
            continue
        source = snapshot / value
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def resolve_patch(
    pack: Path,
    patch_id: str,
    decision: str,
    reason: str,
) -> dict[str, Any]:
    if decision not in {"keep", "revert"}:
        raise EvolutionError("decision must be keep or revert")
    if not reason.strip():
        raise EvolutionError("evolution resolution requires a reason")
    path = pack / "evolution" / "proposals" / f"{patch_id}.json"
    patch = load_json(path)
    if patch["status"] != "applied":
        raise EvolutionError("only applied patches can be resolved")
    if decision == "revert":
        if patch.get("after_hash") != skill_folder_hash(pack):
            raise EvolutionError("Skill folder changed after patch application")
        _restore(pack, patch)
        patch["status"] = "reverted"
        patch["reverted_hash"] = skill_folder_hash(pack)
        if patch["reverted_hash"] != patch["before_hash"]:
            raise EvolutionError("rollback did not restore the original Skill hash")
    else:
        patch["status"] = "kept"
    patch["decision_reason"] = reason.strip()
    patch["resolved_at"] = utc_now()
    _save_patch(path, patch)
    mark_evaluations_stale(pack, f"evolution patch resolved: {patch_id}")
    history = pack / "evolution" / "DECISIONS.jsonl"
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(patch, ensure_ascii=False) + "\n")
    return patch
