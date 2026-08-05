"""Evidence-linked candidate extraction and conservative verification."""

from __future__ import annotations

from collections import defaultdict
import re

from .models import Candidate, Chunk, Evidence
from .profiles import signal_patterns
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
                    notes=f"deterministic {candidate_type} signal; not yet verified",
                )
                evidence.append(record)
                candidates.append(
                    Candidate(
                        title=_title(sentence, candidate_type),
                        candidate_type=candidate_type,
                        summary=sentence,
                        evidence_ids=[record.id],
                        source_contexts=[chunk.section_path],
                        tags=[profile_name, candidate_type],
                    )
                )
                counts[candidate_type] += 1
                break
    return candidates, evidence


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
    return merged


def verify_candidates(candidates: list[Candidate], deep: bool = False) -> list[Candidate]:
    """Apply deterministic gates and never pretend that model-only judgments occurred."""
    for candidate in candidates:
        candidate.cross_domain = len(set(candidate.source_contexts)) >= 2
        candidate.actionable = bool(
            re.search(
                r"(步骤|方法|原则|必须|应该|如果|先|再|检查|step|method|must|should|if)",
                candidate.summary,
                re.IGNORECASE,
            )
        )
        candidate.distinctive = len(set(candidate.summary.split())) >= 6 and len(candidate.summary) >= 28
        # Predictive power requires a model or human to answer a novel question.
        # Deep mode only marks it pending; no heuristic may fabricate this judgment.
        candidate.predictive = False
        if candidate.cross_domain and candidate.actionable and candidate.distinctive:
            candidate.status = "needs_model_verification" if deep else "needs_evidence"
            candidate.rejection_reason = "V2 predictive-power test requires independent model or human review"
        else:
            failed = []
            if not candidate.cross_domain:
                failed.append("V1 requires at least two independent source contexts")
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
