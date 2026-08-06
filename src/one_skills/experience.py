"""Append-only deployment feedback and conservative evolution proposals."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .constants import PERMISSIONS
from .utils import append_jsonl, dump_json, new_id, stable_json_hash, utc_now

OUTCOMES = {"success", "failure", "corrected"}
SCOPES = {"training", "evaluation"}


class ExperienceError(ValueError):
    pass


def _ledger(pack: Path) -> Path:
    return pack / "evolution" / "EXPERIENCE_EVENTS.jsonl"


def _normalize_signature(value: str) -> str:
    words = re.findall(r"[a-zA-Z0-9_-]{2,}|[\u4e00-\u9fff]{2,4}", value.lower())
    return " ".join(words[:24])


def record_experience(
    pack: Path,
    skill: str,
    task_signature: str,
    outcome: str,
    result_summary: str,
    evidence_locator: str,
    correction: str = "",
    access: str = "private-local",
    scope: str = "training",
) -> dict[str, Any]:
    if outcome not in OUTCOMES:
        raise ExperienceError(f"invalid outcome: {outcome}")
    if scope not in SCOPES:
        raise ExperienceError(f"invalid scope: {scope}")
    if access not in PERMISSIONS:
        raise ExperienceError(f"invalid access: {access}")
    for name, value in {
        "skill": skill,
        "task_signature": task_signature,
        "result_summary": result_summary,
        "evidence_locator": evidence_locator,
    }.items():
        if not value.strip():
            raise ExperienceError(f"{name} must not be empty")
    if outcome == "corrected" and not correction.strip():
        raise ExperienceError("corrected outcomes require a correction")
    event = {
        "schema_version": "1.0",
        "id": new_id("experience"),
        "skill": skill,
        "task_signature": task_signature.strip(),
        "normalized_signature": _normalize_signature(task_signature),
        "outcome": outcome,
        "result_summary": result_summary.strip(),
        "correction": correction.strip(),
        "evidence_locator": evidence_locator.strip(),
        "access": access,
        "scope": scope,
        "recorded_at": utc_now(),
    }
    append_jsonl(_ledger(pack), event)
    return event


def load_experiences(pack: Path) -> list[dict[str, Any]]:
    path = _ledger(pack)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExperienceError(f"invalid experience event at line {number}") from exc
        events.append(item)
    return events


def mine_experience_candidates(
    pack: Path,
    minimum_occurrences: int = 2,
) -> dict[str, Any]:
    if minimum_occurrences < 2:
        raise ExperienceError("minimum_occurrences must be at least 2")
    events = load_experiences(pack)
    training = [event for event in events if event.get("scope") == "training"]
    evaluation = [event for event in events if event.get("scope") == "evaluation"]
    groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in training:
        if event.get("outcome") not in {"failure", "corrected"}:
            continue
        groups[(event["skill"], event["normalized_signature"])].append(event)
    candidates: list[dict[str, Any]] = []
    for (skill, signature), group in sorted(groups.items()):
        unique_locators = {event["evidence_locator"] for event in group}
        if len(group) < minimum_occurrences or len(unique_locators) < 2:
            continue
        corrections = list(
            dict.fromkeys(
                event["correction"]
                for event in group
                if event.get("correction")
            )
        )
        candidates.append(
            {
                "id": "evolution-candidate-"
                + stable_json_hash(
                    {
                        "skill": skill,
                        "signature": signature,
                        "events": [event["id"] for event in group],
                    }
                )[:16],
                "skill": skill,
                "pattern": signature,
                "occurrences": len(group),
                "independent_evidence": len(unique_locators),
                "supporting_event_ids": [event["id"] for event in group],
                "proposed_rule": (
                    corrections[-1]
                    if corrections
                    else "Investigate the recurring failure before changing the Skill."
                ),
                "status": "proposed",
                "promotion_gate": (
                    "Run frozen canonical and holdout evaluations; compare before/after; "
                    "require explicit human keep/revert decision."
                ),
            }
        )
    report = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "minimum_occurrences": minimum_occurrences,
        "training_event_ids": [event["id"] for event in training],
        "evaluation_event_ids": [event["id"] for event in evaluation],
        "leakage_barrier": (
            "evaluation events are excluded from candidate mining and remain holdout evidence"
        ),
        "candidates": candidates,
        "candidate_count": len(candidates),
    }
    dump_json(pack / "evolution" / "EXPERIENCE_CANDIDATES.json", report)
    return report
