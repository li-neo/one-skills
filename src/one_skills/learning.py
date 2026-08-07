"""Explicit prerequisite paths and auditable learner mastery state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .utils import dump_json, load_json, slugify, stable_json_hash, utc_now


class LearningError(ValueError):
    pass


def _source_nodes(pack: Path) -> list[dict[str, Any]]:
    chunks = load_json(pack / "sources" / "chunks.json")
    nodes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    previous_by_document: dict[str, str] = {}
    for chunk in chunks:
        key = (chunk["document_id"], chunk["section_path"])
        if key in seen or len(nodes) >= 60:
            continue
        seen.add(key)
        node_id = "concept-" + stable_json_hash(
            {
                "document_id": chunk["document_id"],
                "section": chunk["section_path"],
            }
        )[:16]
        previous = previous_by_document.get(chunk["document_id"])
        nodes.append(
            {
                "id": node_id,
                "title": chunk["section_path"],
                "kind": "source-concept",
                "order": len(nodes),
                "prerequisites": [previous] if previous else [],
                "source_locators": [chunk["source_locator"]],
                "objectives": [
                    f"能够用自己的话解释“{chunk['section_path']}”",
                    "能够指出其适用条件、反例或证据边界",
                ],
                "mastery_checks": [
                    "不看原文复述核心机制",
                    "在一个新场景中正确应用",
                    "说明至少一个不应使用的场景",
                ],
            }
        )
        previous_by_document[chunk["document_id"]] = node_id
    return nodes


def _capability_nodes(pack: Path) -> list[dict[str, Any]]:
    capabilities = []
    module_paths = sorted((pack / "skills").glob("*/capabilities/*.json"))
    paths = module_paths or sorted((pack / "skills").glob("*/capability.json"))
    for path in paths:
        capabilities.append((path.parent.name, load_json(path)))
    if not capabilities:
        return []
    by_capability_id = {
        capability.get("id", skill_name): capability.get("id", skill_name)
        for skill_name, capability in capabilities
    }
    nodes: list[dict[str, Any]] = []
    for order, (skill_name, capability) in enumerate(capabilities):
        node_id = capability.get("id", skill_name)
        prerequisites: list[str] = []
        for relation in capability.get("relations", []):
            if relation.get("relation") not in {"depends_on", "depends-on"}:
                continue
            target = relation.get("target") or relation.get("to")
            if target in by_capability_id:
                prerequisites.append(by_capability_id[target])
            elif isinstance(target, str):
                prerequisites.append(target)
        nodes.append(
            {
                "id": node_id,
                "title": capability["name"],
                "kind": (
                    "executable-capability"
                    if capability.get("status") in {"released", "verified"}
                    else "candidate-capability"
                ),
                "order": order,
                "prerequisites": list(dict.fromkeys(prerequisites)),
                "source_locators": capability.get("evidence_ids", []),
                "objectives": [
                    capability["problem"],
                    f"在“{capability['trigger']}”出现时正确调用",
                ],
                "mastery_checks": [
                    capability["done"],
                    f"能说明边界：{'；'.join(capability.get('boundaries', []))}",
                    f"能从失败中恢复：{capability.get('fallback', '')}",
                ],
            }
        )
    by_id = {node["id"]: node for node in nodes}
    ordered: list[dict[str, Any]] = []
    remaining = set(by_id)
    while remaining:
        ready = sorted(
            node_id
            for node_id in remaining
            if all(
                prerequisite not in by_id
                or prerequisite not in remaining
                for prerequisite in by_id[node_id]["prerequisites"]
            )
        )
        if not ready:
            # validate_learning_path reports the cycle with the exact node.
            ready = sorted(remaining)
        for node_id in ready:
            node = by_id[node_id]
            node["order"] = len(ordered)
            ordered.append(node)
            remaining.remove(node_id)
    return ordered


def validate_learning_path(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = value.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return ["learning path requires at least one node"]
    ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(ids) != len(set(ids)):
        errors.append("learning node IDs must be unique")
    known = set(ids)
    graph: dict[str, list[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("learning nodes must be objects")
            continue
        missing = {
            "id",
            "title",
            "kind",
            "order",
            "prerequisites",
            "source_locators",
            "objectives",
            "mastery_checks",
        } - set(node)
        if missing:
            errors.append(f"node {node.get('id', '?')} missing: {', '.join(sorted(missing))}")
        prerequisites = node.get("prerequisites", [])
        unknown = [item for item in prerequisites if item not in known]
        if unknown:
            errors.append(
                f"node {node.get('id', '?')} has unknown prerequisites: {', '.join(unknown)}"
            )
        graph[node.get("id", "")] = prerequisites

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            errors.append(f"learning path contains a cycle at {node_id}")
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        for prerequisite in graph.get(node_id, []):
            visit(prerequisite)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in graph:
        visit(node_id)
    return list(dict.fromkeys(errors))


def build_learning_path(pack: Path) -> dict[str, Any]:
    metadata = load_json(pack / "pack.json")
    nodes = _capability_nodes(pack) or _source_nodes(pack)
    path = {
        "schema_version": "1.0",
        "pack_id": metadata["id"],
        "profile": metadata["profile"],
        "generated_at": utc_now(),
        "progression": (
            "capability-prerequisite"
            if any(node["kind"] == "executable-capability" for node in nodes)
            else "source-order"
        ),
        "nodes": nodes,
    }
    errors = validate_learning_path(path)
    if errors:
        raise LearningError("; ".join(errors))
    dump_json(pack / "LEARNING_PATH.json", path)
    return path


def init_learner(pack: Path, learner_id: str) -> dict[str, Any]:
    learner_slug = slugify(learner_id)
    path = pack / "LEARNING_PATH.json"
    learning_path = load_json(path) if path.exists() else build_learning_path(pack)
    state_path = pack / "learning" / "states" / f"{learner_slug}.json"
    if state_path.exists():
        raise LearningError(f"learner state already exists: {state_path}")
    state = {
        "schema_version": "1.0",
        "pack_id": learning_path["pack_id"],
        "learner_id": learner_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "mastery": {
            node["id"]: {
                "status": "not_started",
                "score": 0.0,
                "attempts": 0,
                "streak": 0,
                "next_review_at": None,
                "evidence": [],
            }
            for node in learning_path["nodes"]
        },
    }
    dump_json(state_path, state)
    return state


def _state_path(pack: Path, learner_id: str) -> Path:
    return pack / "learning" / "states" / f"{slugify(learner_id)}.json"


def load_learner(pack: Path, learner_id: str) -> dict[str, Any]:
    path = _state_path(pack, learner_id)
    if not path.exists():
        raise LearningError(f"learner state does not exist: {path}")
    return load_json(path)


def record_attempt(
    pack: Path,
    learner_id: str,
    node_id: str,
    score: float,
    evidence: str,
) -> dict[str, Any]:
    if not 0 <= score <= 1:
        raise LearningError("attempt score must be between 0 and 1")
    if not evidence.strip():
        raise LearningError("attempt evidence must not be empty")
    state = load_learner(pack, learner_id)
    if node_id not in state["mastery"]:
        raise LearningError(f"unknown learning node: {node_id}")
    item = state["mastery"][node_id]
    item["attempts"] += 1
    item["score"] = round(
        score if item["attempts"] == 1 else 0.6 * item["score"] + 0.4 * score,
        4,
    )
    if score >= 0.8:
        item["streak"] += 1
        item["status"] = "mastered"
        intervals = (1, 3, 7, 14, 30)
        days = intervals[min(item["streak"] - 1, len(intervals) - 1)]
        item["next_review_at"] = (
            datetime.now(timezone.utc) + timedelta(days=days)
        ).isoformat()
    else:
        item["streak"] = 0
        item["status"] = "learning"
        item["next_review_at"] = (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat()
    item["evidence"].append(
        {
            "recorded_at": utc_now(),
            "score": score,
            "summary": evidence.strip(),
        }
    )
    state["updated_at"] = utc_now()
    dump_json(_state_path(pack, learner_id), state)
    return item


def next_learning_node(pack: Path, learner_id: str) -> dict[str, Any] | None:
    learning_path = load_json(pack / "LEARNING_PATH.json")
    state = load_learner(pack, learner_id)
    now = datetime.now(timezone.utc)
    nodes = sorted(learning_path["nodes"], key=lambda item: item["order"])
    for node in nodes:
        mastery = state["mastery"][node["id"]]
        review = mastery.get("next_review_at")
        if mastery["status"] == "mastered" and review:
            review_at = datetime.fromisoformat(review.replace("Z", "+00:00"))
            if review_at <= now:
                return {**node, "reason": "scheduled_review"}
    for node in nodes:
        mastery = state["mastery"][node["id"]]
        if mastery["status"] == "mastered":
            continue
        if all(
            state["mastery"][required]["status"] == "mastered"
            for required in node["prerequisites"]
        ):
            return {**node, "reason": "next_prerequisite_ready"}
    return None
