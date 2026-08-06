"""Field-aware retrieval for growing Agent Skill libraries."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .retrieval import cosine_similarity, local_embedding, tokenize
from .validation import parse_frontmatter

FIELD_WEIGHTS = {
    "name": 0.15,
    "description": 0.30,
    "triggers": 0.25,
    "procedure": 0.15,
    "body": 0.15,
}


def _sections(body: str) -> dict[str, str]:
    values: dict[str, list[str]] = {"body": []}
    current = "body"
    for line in body.splitlines():
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).lower()
            if re.search(r"激活|调用|触发|何时|场景|when to use|trigger", title):
                current = "triggers"
            elif re.search(r"边界|不适用|不要|反触发|boundary|anti-trigger", title):
                current = "anti_triggers"
            elif re.search(r"步骤|工作流|执行|procedure|workflow|execution", title):
                current = "procedure"
            elif level <= 2:
                current = "body"
            values.setdefault(current, [])
            continue
        values.setdefault(current, []).append(line)
    return {
        field: "\n".join(lines).strip()
        for field, lines in values.items()
    }


def load_skill_record(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    section_values = _sections(body)
    custom_metadata: dict[str, str] = {}
    for line in metadata.get("metadata", "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        custom_metadata[key.strip()] = value.strip().strip("\"'")
    return {
        "path": str(path.parent.resolve()),
        "name": metadata.get("name", path.parent.name),
        "description": metadata.get("description", ""),
        "triggers": section_values.get("triggers", ""),
        "anti_triggers": section_values.get("anti_triggers", ""),
        "procedure": section_values.get("procedure", ""),
        "body": section_values.get("body", ""),
        "activation_mode": custom_metadata.get("one-skills.activation", "auto"),
        "aliases": [
            value.strip()
            for value in custom_metadata.get("one-skills.aliases", "").split(",")
            if value.strip()
        ],
    }


def discover_skills(roots: list[Path]) -> list[dict[str, Any]]:
    seen: set[Path] = set()
    records: list[dict[str, Any]] = []
    for root in roots:
        resolved = root.expanduser().resolve()
        candidates = [resolved / "SKILL.md"] if resolved.is_dir() else []
        if resolved.is_dir():
            candidates.extend(resolved.rglob("SKILL.md"))
        for path in sorted(candidates):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            records.append(load_skill_record(path))
    return records


def _idf(records: list[dict[str, Any]]) -> dict[str, float]:
    frequencies: Counter[str] = Counter()
    for record in records:
        terms = set(
            tokenize(
                " ".join(
                    str(record.get(field, ""))
                    for field in (
                        "name",
                        "description",
                        "triggers",
                        "anti_triggers",
                        "procedure",
                        "body",
                    )
                )
            )
        )
        frequencies.update(terms)
    total = max(len(records), 1)
    return {
        term: math.log((total + 1) / (count + 1)) + 1.0
        for term, count in frequencies.items()
    }


def _lexical_score(query: str, value: str, idf: dict[str, float]) -> float:
    query_terms = set(tokenize(query))
    if not query_terms:
        return 0.0
    field_terms = set(tokenize(value))
    denominator = sum(idf.get(term, 1.0) for term in query_terms)
    if denominator == 0:
        return 0.0
    return sum(
        idf.get(term, 1.0)
        for term in query_terms
        if term in field_terms
    ) / denominator


def _field_score(query: str, value: str, idf: dict[str, float]) -> dict[str, float]:
    lexical = _lexical_score(query, value, idf)
    semantic = cosine_similarity(local_embedding(query), local_embedding(value))
    return {
        "lexical": round(lexical, 4),
        "semantic": round(semantic, 4),
        "combined": round(0.60 * lexical + 0.40 * semantic, 4),
    }


def search_skills(
    query: str,
    roots: list[Path],
    limit: int = 10,
    minimum_score: float = 0.10,
    minimum_margin: float = 0.025,
) -> dict[str, Any]:
    records = discover_skills(roots)
    if not records:
        return {
            "query": query,
            "status": "abstain",
            "reason": "no skills discovered",
            "needs_confirmation": True,
            "results": [],
        }
    idf = _idf(records)
    results: list[dict[str, Any]] = []
    for record in records:
        breakdown = {
            field: _field_score(query, str(record.get(field, "")), idf)
            for field in FIELD_WEIGHTS
        }
        anti = _field_score(query, record.get("anti_triggers", ""), idf)
        score = sum(
            FIELD_WEIGHTS[field] * breakdown[field]["combined"]
            for field in FIELD_WEIGHTS
        )
        explicit_match = record["name"].lower() in query.lower() or any(
            alias.lower() in query.lower() for alias in record["aliases"]
        )
        if explicit_match:
            score += 0.40
        activation_eligible = (
            record["activation_mode"] != "explicit" or explicit_match
        )
        if not activation_eligible:
            score = 0.0
        # Anti-trigger text often repeats domain terms to explain a boundary.
        # Penalize explicit lexical overlap only; semantic similarity would
        # punish well-documented boundaries for mentioning the same domain.
        score -= 0.20 * anti["lexical"]
        results.append(
            {
                "name": record["name"],
                "path": record["path"],
                "description": record["description"],
                "score": round(max(score, 0.0), 4),
                "activation_mode": record["activation_mode"],
                "activation_eligible": activation_eligible,
                "field_scores": breakdown,
                "anti_trigger_score": anti,
            }
        )
    results.sort(key=lambda item: (-item["score"], item["name"]))
    results = results[: max(limit, 1)]
    top = results[0]["score"]
    second = results[1]["score"] if len(results) > 1 else 0.0
    margin = round(top - second, 4)
    if top < minimum_score:
        status = "abstain"
        reason = f"top score {top:.3f} is below {minimum_score:.3f}"
    elif len(results) > 1 and margin < minimum_margin:
        status = "confirm"
        reason = f"top-two margin {margin:.3f} is below {minimum_margin:.3f}"
    else:
        status = "selected"
        reason = "field-aware retrieval passed score and margin gates"
    return {
        "query": query,
        "status": status,
        "reason": reason,
        "needs_confirmation": status != "selected",
        "top_score": top,
        "margin": margin,
        "skill_count": len(records),
        "results": results,
    }
