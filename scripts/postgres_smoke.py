#!/usr/bin/env python3
"""Concurrent PostgreSQL/pgvector smoke and recovery verification."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from statistics import median
from time import perf_counter

from one_skills.postgres import PostgresBackend
from one_skills.utils import new_id, utc_now


def main() -> int:
    dsn = os.environ["ONE_SKILLS_POSTGRES_DSN"]
    query = os.environ.get("ONE_SKILLS_POSTGRES_TEST_QUERY", "瓶颈价值")
    workers = int(os.environ.get("ONE_SKILLS_POSTGRES_TEST_WORKERS", "8"))
    iterations = int(os.environ.get("ONE_SKILLS_POSTGRES_TEST_ITERATIONS", "20"))

    with PostgresBackend(dsn) as backend:
        initial_health = backend.health()
    # A new connection after close verifies reconnect behavior.
    with PostgresBackend(dsn) as backend:
        recovered_health = backend.health()

    def exercise(worker: int) -> list[float]:
        timings = []
        with PostgresBackend(dsn) as backend:
            for index in range(iterations):
                started = perf_counter()
                backend.hybrid_search(
                    query,
                    {"public", "authorized", "private-local"},
                    "local",
                    "local-user",
                )
                timings.append((perf_counter() - started) * 1000)
                with backend.connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO audit_events VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            new_id("audit"),
                            "local",
                            f"ci-worker-{worker}",
                            "ci.concurrent-write",
                            "load-test",
                            str(index),
                            json.dumps({"worker": worker, "iteration": index}),
                            utc_now(),
                        ),
                    )
                backend.connection.commit()
        return timings

    with ThreadPoolExecutor(max_workers=workers) as executor:
        timing_groups = list(executor.map(exercise, range(workers)))
    timings = sorted(value for group in timing_groups for value in group)

    with PostgresBackend(dsn) as backend:
        with backend.connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM audit_events "
                "WHERE action = 'ci.concurrent-write'"
            )
            writes = cursor.fetchone()["count"]
            cursor.execute("DELETE FROM audit_events WHERE action = 'ci.concurrent-write'")
        backend.connection.commit()

    expected = workers * iterations
    report = {
        "initial_ready": initial_health["ready"],
        "recovered_ready": recovered_health["ready"],
        "workers": workers,
        "operations": expected,
        "concurrent_writes": writes,
        "p50_ms": round(median(timings), 3),
        "p95_ms": round(timings[min(len(timings) - 1, int(len(timings) * 0.95))], 3),
        "max_ms": round(max(timings), 3),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not initial_health["ready"] or not recovered_health["ready"] or writes != expected:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
