"""Bounded concurrent execution for independent distillation jobs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sqlite3
from typing import Any

from .pipeline import create_pack, init_workspace, load_state
from .utils import load_json


def load_jobs(path: Path) -> list[dict[str, Any]]:
    value = load_json(path)
    jobs = value.get("jobs") if isinstance(value, dict) else None
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("batch manifest must contain a non-empty jobs array")
    for index, job in enumerate(jobs):
        if not isinstance(job, dict) or not isinstance(job.get("sources"), list) or not job["sources"]:
            raise ValueError(f"batch job {index} requires non-empty sources")
        if not job.get("name"):
            raise ValueError(f"batch job {index} requires a unique name")
    names = [job["name"] for job in jobs]
    if len(names) != len(set(names)):
        raise ValueError("batch job names must be unique")
    return jobs


def distill_batch(
    workspace: Path,
    jobs: list[dict[str, Any]],
    workers: int = 4,
) -> dict[str, Any]:
    if workers < 1 or workers > 32:
        raise ValueError("workers must be between 1 and 32")
    root = init_workspace(workspace)

    def execute(job: dict[str, Any]) -> dict[str, Any]:
        pack = create_pack(
            root,
            job["sources"],
            job.get("type", "auto"),
            job.get("mode", "standard"),
            job["name"],
            job.get("access", "private-local"),
            job.get("consent"),
        )
        state = load_state(pack)
        return {
            "name": job["name"],
            "status": "created",
            "pack": str(pack),
            "phase": state["current_phase"],
        }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as executor:
        futures = {executor.submit(execute, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                results.append(future.result())
            except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
                results.append(
                    {
                        "name": job["name"],
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    results.sort(key=lambda item: item["name"])
    return {
        "workers": min(workers, len(jobs)),
        "total": len(results),
        "created": sum(item["status"] == "created" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "results": results,
    }
