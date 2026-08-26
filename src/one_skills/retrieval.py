"""Local semantic vectors and flat-file hybrid retrieval over Pack chunks."""

from __future__ import annotations

from collections import defaultdict
from hashlib import blake2b
import json
import math
import re
from pathlib import Path
from typing import Any


VECTOR_DIMENSIONS = 128


def tokenize(text: str) -> list[str]:
    english = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{1,}", text.lower())
    chinese: list[str] = []
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            chinese.append(run)
            continue
        for size in (2, 3, 4):
            chinese.extend(run[index : index + size] for index in range(len(run) - size + 1))
    return english + chinese


def local_embedding(text: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float]:
    """Produce a deterministic local feature-hash vector without external calls."""
    vector = [0.0] * dimensions
    tokens = tokenize(text)
    for token in tokens:
        digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: defaultdict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] += 1.0 / (k + rank)
    return dict(scores)


class HybridRetriever:
    """Flat-file hybrid retrieval over a workspace's Pack chunks (no database).

    Scans ``workspace/packs/*/sources/chunks.json`` at construction and runs
    keyword, semantic, and evidence-graph neighborhood search over the in-memory
    rows. Access filtering is a plain ``access_level`` membership check.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace.expanduser().resolve()
        self._rows = self._load_chunks()

    def _load_chunks(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        packs_dir = self.workspace / "packs"
        if not packs_dir.is_dir():
            return rows
        for chunks_path in sorted(packs_dir.glob("*/sources/chunks.json")):
            try:
                chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(chunks, list):
                continue
            pack = chunks_path.parents[1].name
            for chunk in chunks:
                if isinstance(chunk, dict):
                    rows.append({**chunk, "pack": pack})
        return rows

    def _visible(
        self,
        rows: list[dict[str, Any]],
        allowed_access: set[str],
    ) -> list[dict[str, Any]]:
        return [
            row for row in rows if row.get("access_level") in allowed_access
        ]

    def keyword_search(
        self,
        query: str,
        allowed_access: set[str],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        terms = tokenize(query)[:5]
        if not terms:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in self._visible(self._rows, allowed_access):
            text = row.get("text") or ""
            hits = sum(text.count(term) for term in terms)
            if not hits:
                continue
            item = dict(row)
            item["keyword_score"] = float(hits)
            scored.append((float(hits), item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def semantic_search(
        self,
        query: str,
        allowed_access: set[str],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query_vector = local_embedding(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in self._visible(self._rows, allowed_access):
            score = cosine_similarity(query_vector, local_embedding(row.get("text") or ""))
            # Feature hashing is a dependency-free fallback; a floor avoids
            # returning collisions as semantic matches.
            if score < 0.20:
                continue
            item = dict(row)
            item["semantic_score"] = score
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def graph_neighbors(
        self,
        chunk_ids: list[str],
        allowed_access: set[str],
        limit: int = 20,
    ) -> list[str]:
        """Undirected relevance neighborhood: chunks sharing capabilities with the seeds."""
        if not chunk_ids or not allowed_access:
            return []
        seed = set(chunk_ids)
        visible = {row["id"] for row in self._visible(self._rows, allowed_access)}
        claim_by_chunk: defaultdict[str, set[str]] = defaultdict(set)
        capability_by_claim: defaultdict[str, set[str]] = defaultdict(set)
        claim_by_capability: defaultdict[str, set[str]] = defaultdict(set)
        for pack_dir in (self.workspace / "packs").glob("*"):
            ledger = pack_dir / "EVIDENCE_LEDGER.jsonl"
            if ledger.exists():
                try:
                    lines = ledger.read_text(encoding="utf-8").splitlines()
                except OSError:
                    lines = []
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if item.get("chunk_id") and item.get("id"):
                        claim_by_chunk[item["chunk_id"]].add(item["id"])
            for capability_path in (pack_dir / "skills").glob("*/capability.json"):
                try:
                    capability = json.loads(
                        capability_path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    continue
                capability_id = capability.get("id")
                if not capability_id:
                    continue
                for evidence_id in capability.get("evidence_ids", []):
                    capability_by_claim[evidence_id].add(capability_id)
                    claim_by_capability[capability_id].add(evidence_id)
        related_capabilities: set[str] = set()
        for chunk_id in seed:
            for claim_id in claim_by_chunk.get(chunk_id, ()):
                related_capabilities.update(capability_by_claim.get(claim_id, ()))
        related_claims: set[str] = set()
        for capability_id in related_capabilities:
            related_claims.update(claim_by_capability.get(capability_id, ()))
        neighbors = {
            chunk_id
            for chunk_id, claims in claim_by_chunk.items()
            if chunk_id not in seed
            and chunk_id in visible
            and bool(claims & related_claims)
        }
        return sorted(neighbors)[:limit]

    def search(
        self,
        query: str,
        allowed_access: set[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        keyword = self.keyword_search(query, allowed_access, max(limit * 3, 20))
        semantic = self.semantic_search(query, allowed_access, max(limit * 3, 20))
        keyword_ids = [item["id"] for item in keyword]
        semantic_ids = [item["id"] for item in semantic]
        graph_ids = self.graph_neighbors(
            (keyword_ids + semantic_ids)[:10],
            allowed_access,
            limit * 2,
        )
        fused = reciprocal_rank_fusion([keyword_ids, semantic_ids, graph_ids])
        items = {item["id"]: item for item in keyword + semantic}
        results: list[dict[str, Any]] = []
        for item_id, score in sorted(fused.items(), key=lambda pair: pair[1], reverse=True):
            if item_id not in items:
                continue
            item = items[item_id]
            item["score"] = score
            results.append(item)
            if len(results) == limit:
                break
        return results
