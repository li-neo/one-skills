"""Local semantic vectors and ACL-aware hybrid retrieval."""

from __future__ import annotations

from collections import defaultdict
from hashlib import blake2b
import json
import math
import re
from typing import Any

from .database import KnowledgeDB


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
    def __init__(self, database: KnowledgeDB):
        self.database = database

    def _allowed_clause(self, allowed_access: set[str]) -> tuple[str, tuple[str, ...]]:
        if not allowed_access:
            return "0", ()
        placeholders = ", ".join("?" for _ in allowed_access)
        return f"c.access_level IN ({placeholders})", tuple(sorted(allowed_access))

    def keyword_search(
        self,
        query: str,
        allowed_access: set[str],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clause, access_values = self._allowed_clause(allowed_access)
        if self.database.fts_enabled:
            terms = [term.replace('"', "") for term in tokenize(query)[:12]]
            expression = " OR ".join(f'"{term}"' for term in terms)
            if expression:
                rows = self.database.rows(
                    "SELECT c.*, bm25(chunks_fts) AS keyword_score "
                    "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.chunk_id "
                    "JOIN documents d ON d.id = c.document_id "
                    f"WHERE chunks_fts MATCH ? AND {clause} "
                    "AND c.document_version = d.active_version "
                    "ORDER BY keyword_score LIMIT ?",
                    (expression, *access_values, limit),
                )
                return [dict(row) for row in rows]
        patterns = [f"%{term}%" for term in tokenize(query)[:5]]
        if not patterns:
            return []
        conditions = " OR ".join("c.text LIKE ?" for _ in patterns)
        rows = self.database.rows(
            f"SELECT c.*, 0.0 AS keyword_score FROM chunks c "
            "JOIN documents d ON d.id = c.document_id "
            f"WHERE ({conditions}) AND {clause} "
            "AND c.document_version = d.active_version LIMIT ?",
            (*patterns, *access_values, limit),
        )
        return [dict(row) for row in rows]

    def semantic_search(
        self,
        query: str,
        allowed_access: set[str],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clause, access_values = self._allowed_clause(allowed_access)
        rows = self.database.rows(
            "SELECT c.* FROM chunks c JOIN documents d ON d.id = c.document_id "
            f"WHERE {clause} AND c.document_version = d.active_version",
            access_values,
        )
        query_vector = local_embedding(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            item = dict(row)
            try:
                vector = json.loads(item.get("embedding") or "[]")
            except json.JSONDecodeError:
                vector = []
            score = cosine_similarity(query_vector, vector)
            # Feature hashing is a dependency-free fallback; a floor avoids
            # returning collisions as semantic matches.
            if score < 0.20:
                continue
            item["semantic_score"] = score
            scored.append((score, item))
        return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]

    def graph_neighbors(self, chunk_ids: list[str], limit: int = 20) -> list[str]:
        if not chunk_ids:
            return []
        placeholders = ", ".join("?" for _ in chunk_ids)
        rows = self.database.rows(
            "SELECT DISTINCT e2.to_id AS chunk_id "
            "FROM lineage_edges e1 "
            "JOIN lineage_edges e2 ON e1.to_type = e2.from_type AND e1.to_id = e2.from_id "
            f"WHERE e1.from_type = 'chunk' AND e1.from_id IN ({placeholders}) "
            "AND e2.to_type = 'chunk' LIMIT ?",
            (*chunk_ids, limit),
        )
        return [row["chunk_id"] for row in rows]

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
        graph_ids = self.graph_neighbors((keyword_ids + semantic_ids)[:10], limit * 2)
        fused = reciprocal_rank_fusion([keyword_ids, semantic_ids, graph_ids])
        items = {item["id"]: item for item in keyword + semantic}
        missing = [item_id for item_id in graph_ids if item_id not in items]
        if missing:
            placeholders = ", ".join("?" for _ in missing)
            for row in self.database.rows(
                f"SELECT * FROM chunks WHERE id IN ({placeholders})",
                tuple(missing),
            ):
                items[row["id"]] = dict(row)
        results: list[dict[str, Any]] = []
        for item_id, score in sorted(fused.items(), key=lambda pair: pair[1], reverse=True):
            if item_id not in items:
                continue
            item = items[item_id]
            if item["access_level"] not in allowed_access:
                continue
            item["score"] = score
            results.append(item)
            if len(results) == limit:
                break
        return results
