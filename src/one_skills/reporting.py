"""Human-readable reports generated from authoritative structured state."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re

from .database import KnowledgeDB
from .utils import atomic_write, load_json


def _node_id(node_type: str, value: str) -> str:
    return "n" + sha256(f"{node_type}:{value}".encode()).hexdigest()[:12]


def _label(node_type: str, value: str) -> str:
    cleaned = re.sub(r"[\[\]\"{}]", "", value)
    return f"{node_type}: {cleaned[:48]}"


def write_evidence_graph(pack: Path, database: KnowledgeDB) -> Path:
    manifest = load_json(pack / "SOURCE_MANIFEST.json")
    capabilities = [
        load_json(path)
        for path in sorted((pack / "skills").glob("*/capability.json"))
    ]
    known: set[tuple[str, str]] = set()
    for source in manifest["sources"]:
        known.add(("source", source["source_id"]))
        known.add(("document", source["document_id"]))
        known.update(("chunk", chunk_id) for chunk_id in source["chunk_ids"])
    for capability in capabilities:
        known.add(("capability", capability["id"]))
        known.update(("claim", evidence_id) for evidence_id in capability["evidence_ids"])
    known.update(("skill", path.parent.name) for path in (pack / "skills").glob("*/SKILL.md"))

    edges = []
    for row in database.rows(
        "SELECT from_type, from_id, relation, to_type, to_id FROM lineage_edges"
    ):
        source = (row["from_type"], row["from_id"])
        target = (row["to_type"], row["to_id"])
        if source in known and target in known:
            edges.append(dict(row))

    lines = [
        "# Evidence Graph",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    emitted: set[tuple[str, str]] = set()
    for edge in edges:
        source = (edge["from_type"], edge["from_id"])
        target = (edge["to_type"], edge["to_id"])
        for node in (source, target):
            if node not in emitted:
                lines.append(
                    f'  {_node_id(*node)}["{_label(*node)}"]'
                )
                emitted.add(node)
        relation = re.sub(r"[^a-zA-Z0-9_-]", "", edge["relation"])
        lines.append(f"  {_node_id(*source)} -->|{relation}| {_node_id(*target)}")
    if not edges:
        lines.append('  empty["No linked evidence"]')
    lines.extend(["```", "", f"Nodes: {len(emitted)}; edges: {len(edges)}.", ""])
    path = pack / "reports" / "EVIDENCE_GRAPH.md"
    atomic_write(path, "\n".join(lines))
    return path
