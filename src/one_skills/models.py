"""Typed intermediate representation for all distillation profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .constants import EVIDENCE_TYPES, INFERENCE_LEVELS, PERMISSIONS
from .utils import new_id, utc_now


@dataclass(frozen=True)
class SourceDocument:
    source: str
    title: str
    media_type: str
    text: str
    content_hash: str
    byte_count: int
    access_level: str = "private-local"
    license: str | None = None
    extractor: str = "plain-text"
    warnings: tuple[str, ...] = ()
    authority: str = "unknown"
    directness: str = "unknown"
    independence_group: str = ""
    source_role: str = "evidence"
    source_uri: str | None = None
    creator: str | None = None
    published_at: str | None = None
    quality_score: float = 0.0

    def metadata(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("text")
        result["character_count"] = len(self.text)
        return result


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    document_version: int
    section_path: str
    ordinal: int
    text: str
    content_hash: str
    access_level: str
    source_locator: str
    source_key: str = ""
    independence_group: str = ""
    authority: str = "unknown"
    source_role: str = "evidence"


@dataclass(frozen=True)
class Evidence:
    claim: str
    evidence_type: str
    source: str
    locator: str
    confidence: float
    inference_level: str
    permission: str
    source_key: str = ""
    independence_group: str = ""
    authority: str = "unknown"
    chunk_id: str = ""
    document_version: int | None = None
    id: str = field(default_factory=lambda: new_id("ev"))
    notes: str = ""
    recorded_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if self.evidence_type not in EVIDENCE_TYPES:
            raise ValueError(f"invalid evidence_type: {self.evidence_type}")
        if self.inference_level not in INFERENCE_LEVELS:
            raise ValueError(f"invalid inference_level: {self.inference_level}")
        if self.permission not in PERMISSIONS:
            raise ValueError(f"invalid permission: {self.permission}")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        for name in ("claim", "source", "locator"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass
class ObjectOverview:
    profile: str
    subject: str
    thesis: str
    structure: list[dict[str, Any]]
    key_terms: list[dict[str, str]]
    mechanism_chain: list[str]
    timeline_or_state_model: list[str]
    tensions: list[str]
    limitations: list[str]
    research_gaps: list[str]
    source_coverage: dict[str, list[str]]
    id: str = field(default_factory=lambda: new_id("overview"))
    status: str = "candidate"
    generated_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if not self.profile or not self.subject or not self.thesis:
            raise ValueError("Object Overview requires profile, subject, and thesis")
        if not self.structure:
            raise ValueError("Object Overview requires a non-empty structure")
        if self.status not in {"candidate", "confirmed", "stale"}:
            raise ValueError(f"invalid Object Overview status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass
class Candidate:
    title: str
    candidate_type: str
    summary: str
    evidence_ids: list[str]
    source_contexts: list[str]
    tags: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    independence_groups: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("candidate"))
    cross_domain: bool = False
    source_independent: bool = False
    predictive: bool = False
    distinctive: bool = False
    actionable: bool = False
    status: str = "pending"
    rejection_reason: str = ""
    problem: str = ""
    assumptions: list[str] = field(default_factory=list)
    mechanism: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    anti_triggers: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    procedure: list[str] = field(default_factory=list)
    branches: list[dict[str, str]] = field(default_factory=list)
    output: str = ""
    done: str = ""
    boundaries: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    counterexamples: list[str] = field(default_factory=list)
    related_ids: list[dict[str, str]] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    disposition: str = "independent-module"

    @property
    def accepted(self) -> bool:
        return all((self.cross_domain, self.predictive, self.distinctive, self.actionable))


@dataclass
class Capability:
    name: str
    problem: str
    trigger: str
    inputs: list[str]
    procedure: list[str]
    output: str
    done: str
    boundaries: list[str]
    failures: list[str]
    fallback: str
    evidence_ids: list[str]
    confidence: float
    id: str = field(default_factory=lambda: new_id("capability"))
    relations: list[dict[str, str]] = field(default_factory=list)
    anti_triggers: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    branches: list[dict[str, str]] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    module_type: str = "internal"
    status: str = "candidate"

    def validate(self) -> None:
        required = {
            "name": self.name,
            "problem": self.problem,
            "trigger": self.trigger,
            "output": self.output,
            "done": self.done,
            "fallback": self.fallback,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"capability fields are empty: {', '.join(missing)}")
        if not self.procedure:
            raise ValueError("capability procedure must not be empty")
        if not self.evidence_ids:
            raise ValueError("capability must link to evidence")
        if not 0 <= self.confidence <= 1:
            raise ValueError("capability confidence must be between 0 and 1")
        if self.module_type not in {"entry", "internal", "governance", "standalone"}:
            raise ValueError(f"invalid capability module_type: {self.module_type}")
        if self.status not in {
            "candidate",
            "supporting",
            "verified",
            "released",
            "stale",
        }:
            raise ValueError(f"invalid capability status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class GraphEdge:
    from_type: str
    from_id: str
    relation: str
    to_type: str
    to_id: str
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 1.0
    status: str = "candidate"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class EvaluationRecord:
    id: str
    case_id: str
    condition: str
    prompt: str
    answer: str
    passed: bool
    scores: dict[str, float]
    judge_reason: str
    answer_model: str
    judge_model: str
    isolation_level: str
    hashes: dict[str, str]
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TestCase:
    id: str
    test_type: str
    prompt: str
    expected: str
    risk: str = "low"
    sibling_skill: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.test_type,
            "prompt": self.prompt,
            "expected": self.expected,
            "risk": self.risk,
            "sibling_skill": self.sibling_skill,
        }
