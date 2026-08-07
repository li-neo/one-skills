"""Evidence-linked capability graph and deterministic projections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .database import KnowledgeDB
from .models import Candidate, Capability, GraphEdge
from .utils import dump_json, load_json, stable_json_hash

ALLOWED_RELATIONS = {
    "supports",
    "contradicts",
    "depends_on",
    "contrasts_with",
    "composes_with",
    "invalidates",
    "routes_to",
    "hands_off_to",
    "rolls_back_to",
    "reads",
    "writes",
    "verifies",
    "shadows",
    "supersedes",
}


class CapabilityGraphError(ValueError):
    pass


def _assert_acyclic(edges: list[dict[str, Any]]) -> None:
    graph: dict[str, list[str]] = {}
    for edge in edges:
        if edge["relation"] != "depends_on":
            continue
        graph.setdefault(edge["from_id"], []).append(edge["to_id"])
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise CapabilityGraphError(f"capability dependency cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for target in graph.get(node, []):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def build_capability_graph(
    pack: Path,
    capabilities: list[Capability],
    candidates: list[Candidate],
) -> dict[str, Any]:
    metadata = load_json(pack / "pack.json")
    nodes: list[dict[str, Any]] = [
        {
            "id": "governance-evidence-boundary",
            "type": "governance",
            "title": "证据、版本、安全与权利治理门",
            "status": "verified",
            "evidence_ids": [],
        }
    ]
    edges: list[GraphEdge] = []
    by_candidate = {item.id: item for item in candidates}
    by_title = {item.title: item for item in candidates}
    for capability in capabilities:
        candidate = by_candidate.get(capability.id) or by_title.get(capability.name)
        evidence_ids = capability.evidence_ids
        nodes.append(
            {
                "id": capability.id,
                "type": "capability",
                "title": capability.name,
                "status": capability.status,
                "evidence_ids": evidence_ids,
            }
        )
        edges.append(
            GraphEdge(
                from_type="capability",
                from_id=capability.id,
                relation="depends_on",
                to_type="governance",
                to_id="governance-evidence-boundary",
                evidence_ids=tuple(evidence_ids),
                confidence=1.0,
                status="verified",
            )
        )
        for evidence_id in evidence_ids:
            claim_id = f"claim-{evidence_id}"
            nodes.append(
                {
                    "id": claim_id,
                    "type": "claim",
                    "title": evidence_id,
                    "status": "verified",
                    "evidence_ids": [evidence_id],
                }
            )
            edges.append(
                GraphEdge(
                    from_type="claim",
                    from_id=claim_id,
                    relation="supports",
                    to_type="capability",
                    to_id=capability.id,
                    evidence_ids=(evidence_id,),
                    confidence=capability.confidence,
                    status="verified",
                )
            )
        relations = capability.relations or (
            candidate.related_ids if candidate else []
        )
        for relation in relations:
            relation_name = relation.get("relation", "")
            target = relation.get("target") or relation.get("to")
            if relation_name not in ALLOWED_RELATIONS or not target:
                continue
            edges.append(
                GraphEdge(
                    from_type="capability",
                    from_id=capability.id,
                    relation=relation_name,
                    to_type="capability",
                    to_id=str(target),
                    evidence_ids=tuple(evidence_ids),
                    confidence=0.75,
                    status="candidate",
                )
            )
    for candidate in candidates:
        if candidate.disposition not in {"case", "counterexample", "term"}:
            continue
        node_type = (
            "counterexample"
            if candidate.disposition == "counterexample"
            else candidate.disposition
        )
        nodes.append(
            {
                "id": candidate.id,
                "type": node_type,
                "title": candidate.title,
                "status": "candidate",
                "evidence_ids": candidate.evidence_ids,
            }
        )

    deduplicated_nodes = {
        (node["type"], node["id"]): node
        for node in nodes
    }
    edge_values = [edge.to_dict() for edge in edges]
    _assert_acyclic(edge_values)
    value = {
        "schema_version": "1.0",
        "pack_id": metadata["id"],
        "nodes": list(deduplicated_nodes.values()),
        "edges": edge_values,
    }
    dump_json(pack / "CAPABILITY_GRAPH.json", value)
    graph_hash = stable_json_hash(value)
    metadata["capability_graph_hash"] = graph_hash
    dump_json(pack / "pack.json", metadata)
    constraints = load_json(pack / "PROTECTED_CONSTRAINTS.json")
    constraints["capability_graph_hash"] = graph_hash
    dump_json(pack / "PROTECTED_CONSTRAINTS.json", constraints)
    from .pipeline import workspace_for

    workspace = workspace_for(pack)
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        database.clear_pack_graph(metadata["id"])
        for edge in edges:
            database.add_graph_edge(
                metadata["id"],
                edge.from_type,
                edge.from_id,
                edge.relation,
                edge.to_type,
                edge.to_id,
                list(edge.evidence_ids),
                edge.confidence,
                edge.status,
            )
    return value
