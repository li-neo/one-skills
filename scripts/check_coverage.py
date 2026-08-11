#!/usr/bin/env python3
"""Enforce the Stable Core aggregate line-coverage gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

STABLE_CORE = {
    "src/one_skills/artifacts.py",
    "src/one_skills/capability_graph.py",
    "src/one_skills/compiler.py",
    "src/one_skills/compilers/__init__.py",
    "src/one_skills/core_assets.py",
    "src/one_skills/database.py",
    "src/one_skills/delivery.py",
    "src/one_skills/distillation_quality.py",
    "src/one_skills/evaluation.py",
    "src/one_skills/evaluation_state.py",
    "src/one_skills/extraction.py",
    "src/one_skills/lifecycle.py",
    "src/one_skills/locking.py",
    "src/one_skills/models.py",
    "src/one_skills/pipeline.py",
    "src/one_skills/provenance.py",
    "src/one_skills/retrieval.py",
    "src/one_skills/schema_runtime.py",
    "src/one_skills/skill_retrieval.py",
    "src/one_skills/source_workflow.py",
}
MINIMUM_PERCENT = 85.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    value = json.loads(args.report.read_text(encoding="utf-8"))
    files = value["files"]
    missing = sorted(STABLE_CORE - set(files))
    if missing:
        raise SystemExit(f"coverage report is missing Stable Core files: {missing}")
    statements = sum(
        files[path]["summary"]["num_statements"] for path in STABLE_CORE
    )
    covered = sum(
        files[path]["summary"]["covered_lines"] for path in STABLE_CORE
    )
    percent = 100.0 * covered / statements
    print(
        f"Stable Core line coverage: {covered}/{statements} "
        f"({percent:.2f}%, required {MINIMUM_PERCENT:.2f}%)"
    )
    if percent < MINIMUM_PERCENT:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
