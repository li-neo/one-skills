"""Evaluation validity transitions after authoritative Pack changes."""

from __future__ import annotations

from pathlib import Path

from .utils import dump_json, load_json, utc_now


def mark_evaluations_stale(pack: Path, reason: str) -> list[str]:
    changed: list[str] = []
    for relative in (
        "evaluations/comparison-report.json",
        "test-results.json",
    ):
        path = pack / relative
        if not path.exists():
            continue
        value = load_json(path)
        if value.get("status") == "stale" and value.get("stale_reason") == reason:
            continue
        value["status"] = "stale"
        value["stale_reason"] = reason
        value["stale_at"] = utc_now()
        dump_json(path, value)
        changed.append(relative)
    return changed
