"""Reproducible benchmark runner for Recipe and Profile changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import SourceDocument
from .profiles import detect_profile
from .utils import dump_json, load_json, sha256_bytes, utc_now


def run_profile_benchmark(suite_path: Path, report_path: Path | None = None) -> dict[str, Any]:
    suite = load_json(suite_path)
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("benchmark suite must contain non-empty cases")
    results = []
    for case in cases:
        text = case["text"]
        document = SourceDocument(
            source=f"benchmark:{case['id']}",
            title=case["title"],
            media_type="text/plain",
            text=text,
            content_hash=sha256_bytes(text.encode("utf-8")),
            byte_count=len(text.encode("utf-8")),
            access_level="public",
        )
        actual = detect_profile([document], [])
        results.append(
            {
                "id": case["id"],
                "expected": case["expected"],
                "actual": actual,
                "passed": actual == case["expected"],
            }
        )
    passed = sum(item["passed"] for item in results)
    report = {
        "suite": suite["name"],
        "generated_at": utc_now(),
        "evaluated": len(results),
        "passed": passed,
        "rate": passed / len(results),
        "results": results,
    }
    if report_path:
        dump_json(report_path, report)
    return report
