"""Evidence-linked candidate extraction and conservative verification."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .models import Candidate, Chunk, Evidence
from .profiles import PROFILES, profile_prompt, signal_patterns
from .provider import ModelProvider, ProviderError
from .retrieval import tokenize
from .utils import slugify


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    return [part.strip() for part in parts if 20 <= len(part.strip()) <= 500]


def _title(sentence: str, candidate_type: str) -> str:
    cleaned = re.sub(r"[`*_#>\[\]\"“”]", "", sentence).strip()
    if len(cleaned) > 42:
        cleaned = cleaned[:42].rstrip("，,；;：: ") + "..."
    return cleaned or candidate_type


def extract_candidates(
    chunks: list[Chunk],
    profile_name: str,
    limit_per_type: int = 20,
) -> tuple[list[Candidate], list[Evidence]]:
    """Generate auditable candidates; the output remains explicitly unverified."""
    patterns = signal_patterns(profile_name)
    candidates: list[Candidate] = []
    evidence: list[Evidence] = []
    counts: defaultdict[str, int] = defaultdict(int)
    seen: set[str] = set()
    for chunk in chunks:
        for sentence in _sentences(chunk.text):
            normalized = re.sub(r"\s+", "", sentence.lower())
            signature = slugify(normalized[:80])
            if signature in seen:
                continue
            for candidate_type, pattern in patterns.items():
                if counts[candidate_type] >= limit_per_type or not pattern.search(sentence):
                    continue
                seen.add(signature)
                record = Evidence(
                    claim=sentence,
                    evidence_type="quote",
                    source=chunk.document_id,
                    locator=chunk.source_locator,
                    confidence=0.8,
                    inference_level="none",
                    permission=chunk.access_level,
                    source_key=chunk.source_key,
                    independence_group=chunk.independence_group,
                    authority=chunk.authority,
                    chunk_id=chunk.id,
                    document_version=chunk.document_version,
                    notes=f"deterministic {candidate_type} signal; not yet verified",
                )
                evidence.append(record)
                candidates.append(
                    Candidate(
                        title=_title(sentence, candidate_type),
                        candidate_type=candidate_type,
                        summary=sentence,
                        evidence_ids=[record.id],
                        source_contexts=[
                            f"{chunk.source_key or chunk.document_id}::{chunk.section_path}"
                        ],
                        source_ids=[chunk.source_key or chunk.document_id],
                        independence_groups=[
                            chunk.independence_group
                            or chunk.source_key
                            or chunk.document_id
                        ],
                        tags=[profile_name, candidate_type],
                    )
                )
                counts[candidate_type] += 1
                break
    return candidates, evidence


def extract_structured_claims(
    chunks: list[Chunk],
    profile_name: str,
) -> tuple[list[Candidate], list[Evidence]]:
    """Materialize curator-declared claim families without semantic guessing.

    Captured sources may include a compact block with ``Claim-Key``,
    ``Claim-Statement``, ``Claim-Type``, and ``Evidence`` lines. Reusing the
    same key across sources declares recurrence; independent provenance is
    still computed from source metadata rather than trusted from the marker.
    """
    grouped: defaultdict[str, list[tuple[Chunk, str, str, str]]] = defaultdict(list)
    for chunk in chunks:
        key = re.search(r"(?m)^Claim-Key:\s*([a-z0-9][a-z0-9-]{1,63})\s*$", chunk.text)
        statement = re.search(r"(?m)^Claim-Statement:\s*(.+?)\s*$", chunk.text)
        evidence = re.search(r"(?m)^Evidence:\s*(.+?)\s*$", chunk.text)
        claim_type = re.search(r"(?m)^Claim-Type:\s*([a-z0-9_-]+)\s*$", chunk.text)
        if not key or not statement or not evidence:
            continue
        grouped[key.group(1)].append(
            (
                chunk,
                statement.group(1).strip(),
                evidence.group(1).strip(),
                claim_type.group(1) if claim_type else "framework",
            )
        )
    candidates: list[Candidate] = []
    records: list[Evidence] = []
    for claim_key, values in sorted(grouped.items()):
        statements = {value[1] for value in values}
        claim_types = {value[3] for value in values}
        if len(statements) != 1 or len(claim_types) != 1:
            raise ValueError(
                f"structured claim {claim_key} has conflicting statements or types"
            )
        evidence_ids: list[str] = []
        contexts: list[str] = []
        source_ids: list[str] = []
        groups: list[str] = []
        for chunk, _, quote, _ in values:
            record = Evidence(
                claim=quote,
                evidence_type="quote",
                source=chunk.document_id,
                locator=chunk.source_locator,
                confidence=0.9,
                inference_level="none",
                permission=chunk.access_level,
                source_key=chunk.source_key,
                independence_group=chunk.independence_group,
                authority=chunk.authority,
                chunk_id=chunk.id,
                document_version=chunk.document_version,
                notes=f"structured claim family: {claim_key}",
            )
            records.append(record)
            evidence_ids.append(record.id)
            contexts.append(
                f"{chunk.source_key or chunk.document_id}::{chunk.section_path}"
            )
            source_ids.append(chunk.source_key or chunk.document_id)
            groups.append(
                chunk.independence_group
                or chunk.source_key
                or chunk.document_id
            )
        statement = next(iter(statements))
        candidates.append(
            Candidate(
                title=claim_key,
                candidate_type=next(iter(claim_types)),
                summary=statement,
                evidence_ids=evidence_ids,
                source_contexts=list(dict.fromkeys(contexts)),
                source_ids=list(dict.fromkeys(source_ids)),
                independence_groups=list(dict.fromkeys(groups)),
                tags=[profile_name, "structured-claim", claim_key],
            )
        )
    return candidates, records


def merge_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Merge candidates only when normalized titles substantially overlap."""
    merged: list[Candidate] = []
    for candidate in candidates:
        terms = set(re.findall(r"[a-zA-Z0-9_-]{2,}|[\u4e00-\u9fff]{2,4}", candidate.title.lower()))
        match = None
        for existing in merged:
            existing_terms = set(
                re.findall(r"[a-zA-Z0-9_-]{2,}|[\u4e00-\u9fff]{2,4}", existing.title.lower())
            )
            union = terms | existing_terms
            if union and len(terms & existing_terms) / len(union) >= 0.65:
                match = existing
                break
        if match is None:
            merged.append(candidate)
            continue
        match.evidence_ids.extend(
            evidence_id for evidence_id in candidate.evidence_ids if evidence_id not in match.evidence_ids
        )
        match.source_contexts.extend(
            context for context in candidate.source_contexts if context not in match.source_contexts
        )
        match.source_ids.extend(
            source_id
            for source_id in candidate.source_ids
            if source_id not in match.source_ids
        )
        match.independence_groups.extend(
            group
            for group in candidate.independence_groups
            if group not in match.independence_groups
        )
    return merged


def verify_candidates(
    candidates: list[Candidate],
    deep: bool = False,
    require_independent_sources: bool = False,
) -> list[Candidate]:
    """Apply deterministic gates and never pretend that model-only judgments occurred."""
    for candidate in candidates:
        candidate.cross_domain = len(set(candidate.source_contexts)) >= 2
        candidate.source_independent = len(set(candidate.independence_groups)) >= 2
        candidate.actionable = bool(
            re.search(
                r"(步骤|方法|原则|必须|应该|如果|先|再|检查|step|method|must|should|if)",
                candidate.summary,
                re.IGNORECASE,
            )
        )
        candidate.distinctive = (
            len(set(tokenize(candidate.summary))) >= 6
            and len(candidate.summary) >= 28
        )
        # Predictive power requires a model or human to answer a novel question.
        # Deep mode only marks it pending; no heuristic may fabricate this judgment.
        candidate.predictive = False
        source_gate = candidate.source_independent or not require_independent_sources
        if (
            candidate.cross_domain
            and source_gate
            and candidate.actionable
            and candidate.distinctive
        ):
            candidate.status = "needs_model_verification" if deep else "needs_evidence"
            candidate.rejection_reason = "V2 predictive-power test requires independent model or human review"
        else:
            failed = []
            if not candidate.cross_domain:
                failed.append("V1 requires recurrence in at least two source contexts")
            if require_independent_sources and not candidate.source_independent:
                failed.append(
                    "the selected Profile requires two independent provenance groups"
                )
            if not candidate.actionable:
                failed.append("candidate is not yet executable")
            if not candidate.distinctive:
                failed.append("candidate may be generic or underspecified")
            candidate.status = "rejected"
            candidate.rejection_reason = "; ".join(failed)
    return candidates


def approve_candidate(candidate: Candidate, predictive_reason: str) -> Candidate:
    if not predictive_reason.strip():
        raise ValueError("predictive verification reason must not be empty")
    candidate.predictive = True
    if candidate.cross_domain and candidate.distinctive and candidate.actionable:
        candidate.status = "accepted"
        candidate.rejection_reason = ""
    return candidate


def extract_candidates_with_model(
    provider: ModelProvider,
    chunks: list[Chunk],
    profile_name: str,
    workers: int = 5,
) -> tuple[list[Candidate], list[Evidence]]:
    """Run independent semantic views and accept only verbatim chunk evidence."""
    if profile_name not in PROFILES:
        raise ValueError(f"unknown profile: {profile_name}")
    if not chunks:
        return [], []
    views = PROFILES[profile_name].candidate_kinds
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    payload_chunks = []
    character_budget = 50000
    used = 0
    for chunk in chunks:
        if used >= character_budget:
            break
        text = chunk.text[: min(len(chunk.text), character_budget - used)]
        payload_chunks.append(
            {
                "id": chunk.id,
                "section": chunk.section_path,
                "locator": chunk.source_locator,
                "text": text,
            }
        )
        used += len(text)

    def run_view(view: str) -> dict:
        return provider.complete_json(
            (
                f"You are the independent {view} extractor in a multi-view distillation pipeline. "
                "Return JSON {candidates:[...]}. Each candidate must contain title, summary, tags, "
                "and evidence. Evidence items must contain chunk_id and a verbatim quote copied "
                "from that chunk. Do not evaluate or compile Skills."
            ),
            json.dumps(
                {
                    "profile_contract": profile_prompt(profile_name),
                    "view": view,
                    "chunks": payload_chunks,
                },
                ensure_ascii=False,
            ),
            f"extract-{view}",
        )

    with ThreadPoolExecutor(max_workers=min(workers, len(views))) as executor:
        outputs = list(executor.map(run_view, views))

    candidates: list[Candidate] = []
    evidence_records: list[Evidence] = []
    for view, output in zip(views, outputs):
        values = output.get("candidates")
        if not isinstance(values, list):
            raise ProviderError(f"extract-{view} response requires candidates array")
        for value in values[:20]:
            if not isinstance(value, dict):
                raise ProviderError(f"extract-{view} candidate must be an object")
            title = value.get("title")
            summary = value.get("summary")
            evidence_values = value.get("evidence")
            if (
                not isinstance(title, str)
                or not title.strip()
                or not isinstance(summary, str)
                or not summary.strip()
                or not isinstance(evidence_values, list)
                or not evidence_values
            ):
                raise ProviderError(f"extract-{view} candidate is incomplete")
            evidence_ids: list[str] = []
            contexts: list[str] = []
            for item in evidence_values:
                if not isinstance(item, dict):
                    raise ProviderError(f"extract-{view} evidence must be an object")
                chunk = chunk_by_id.get(item.get("chunk_id"))
                quote = item.get("quote")
                if chunk is None or not isinstance(quote, str) or quote.strip() not in chunk.text:
                    raise ProviderError(
                        f"extract-{view} evidence quote is not verbatim in its chunk"
                    )
                record = Evidence(
                    claim=quote.strip(),
                    evidence_type="quote",
                    source=chunk.document_id,
                    locator=chunk.source_locator,
                    confidence=0.9,
                    inference_level="none",
                    permission=chunk.access_level,
                    source_key=chunk.source_key,
                    independence_group=chunk.independence_group,
                    authority=chunk.authority,
                    chunk_id=chunk.id,
                    document_version=chunk.document_version,
                    notes=f"semantic {view} extractor",
                )
                evidence_records.append(record)
                evidence_ids.append(record.id)
                contexts.append(
                    f"{chunk.source_key or chunk.document_id}::{chunk.section_path}"
                )
            tags = value.get("tags", [])
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise ProviderError(f"extract-{view} tags must be a string array")
            candidates.append(
                Candidate(
                    title=title.strip(),
                    candidate_type=view,
                    summary=summary.strip(),
                    evidence_ids=evidence_ids,
                    source_contexts=list(dict.fromkeys(contexts)),
                    source_ids=list(
                        dict.fromkeys(
                            chunk_by_id[item["chunk_id"]].source_key
                            or chunk_by_id[item["chunk_id"]].document_id
                            for item in evidence_values
                        )
                    ),
                    independence_groups=list(
                        dict.fromkeys(
                            chunk_by_id[item["chunk_id"]].independence_group
                            or chunk_by_id[item["chunk_id"]].source_key
                            or chunk_by_id[item["chunk_id"]].document_id
                            for item in evidence_values
                        )
                    ),
                    tags=[profile_name, view, *tags],
                )
            )
    return merge_candidates(candidates), evidence_records
