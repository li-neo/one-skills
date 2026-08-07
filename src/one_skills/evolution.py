"""Structured, reversible whole-folder Skill evolution patches."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .experience import load_experiences
from .utils import dump_json, load_json, new_id, stable_json_hash, utc_now


class EvolutionError(ValueError):
    pass


VALID_ACTIONS = {"CREATE", "UPDATE", "MERGE", "PRUNE", "NOOP"}
PROTECTED_PARTS = {"evals", "test-prompts.json"}


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
    dump_json(directory / f"{patch['id']}.json", patch)
    return patch


def _snapshot(pack: Path, patch: dict[str, Any]) -> Path:
    root = pack / "evolution" / "snapshots" / patch["id"]
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
    if patch["status"] != "proposed":
        raise EvolutionError("only proposed patches can be applied")
    required = {"before_score", "after_score", "hard_gates"}
    if not required <= set(comparison):
        raise EvolutionError("comparison requires before_score, after_score, and hard_gates")
    if (
        float(comparison["after_score"]) <= float(comparison["before_score"])
        or not all(comparison["hard_gates"].values())
    ):
        patch["status"] = "rejected"
        patch["comparison"] = comparison
        patch["decision_reason"] = "candidate did not improve or failed a protected gate"
        dump_json(path, patch)
        return patch
    if patch["before_hash"] != skill_folder_hash(pack):
        raise EvolutionError("Skill folder changed after patch proposal")
    _snapshot(pack, patch)
    _apply(pack, patch)
    patch["after_hash"] = skill_folder_hash(pack)
    patch["comparison"] = comparison
    patch["status"] = "applied"
    patch["applied_at"] = utc_now()
    dump_json(path, patch)
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
        _restore(pack, patch)
        patch["status"] = "reverted"
        patch["reverted_hash"] = skill_folder_hash(pack)
        if patch["reverted_hash"] != patch["before_hash"]:
            raise EvolutionError("rollback did not restore the original Skill hash")
    else:
        patch["status"] = "kept"
    patch["decision_reason"] = reason.strip()
    patch["resolved_at"] = utc_now()
    dump_json(path, patch)
    history = pack / "evolution" / "DECISIONS.jsonl"
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(patch, ensure_ascii=False) + "\n")
    return patch
