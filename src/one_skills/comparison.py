"""Blind, role-separated evaluation and weighted baseline comparison."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .core_assets import (
    load_reproducibility,
    load_source_manifest,
    save_reproducibility,
)
from .models import EvaluationRecord
from .utils import dump_json, load_json, new_id, stable_json_hash, utc_now
from .validation import validate_pack


class ComparisonError(ValueError):
    pass


def _request_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "one-skills/0.3",
    }
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        headers=headers,
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_github_skill_context(repository: str, commit: str) -> str:
    tree = _request_json(
        f"https://api.github.com/repos/{repository}/git/trees/{commit}?recursive=1"
    )
    paths = [
        item["path"]
        for item in tree.get("tree", [])
        if item.get("type") == "blob"
        and (
            item["path"] == "SKILL.md"
            or item["path"].endswith("/SKILL.md")
        )
    ]
    documents: list[str] = []
    for path in paths:
        value = _request_json(
            f"https://api.github.com/repos/{repository}/contents/"
            f"{quote(path)}?ref={commit}"
        )
        content = base64.b64decode(value["content"]).decode("utf-8")
        documents.append(f"# FILE: {path}\n\n{content}")
    if not documents:
        raise ComparisonError(f"baseline has no SKILL.md files: {repository}@{commit}")
    return "\n\n".join(documents)


def local_skill_context(pack: Path) -> str:
    files = sorted((pack / "skills").glob("*/SKILL.md"))
    files.extend(sorted((pack / "skills").glob("*/references/**/*.md")))
    if not files:
        raise ComparisonError(f"Pack has no compiled Skill context: {pack}")
    return "\n\n".join(
        f"# FILE: {path.relative_to(pack)}\n\n{path.read_text(encoding='utf-8')}"
        for path in files
    )


def _rate(records: list[dict[str, Any]], types: set[str]) -> float:
    selected = [item for item in records if item["case_type"] in types]
    return (
        sum(bool(item["passed"]) for item in selected) / len(selected)
        if selected
        else 0.0
    )


def _dimension_average(records: list[dict[str, Any]], dimension: str) -> float:
    values = [
        float(item.get("scores", {}).get(dimension, 0.0))
        for item in records
        if dimension in item.get("scores", {})
    ]
    return sum(values) / len(values) if values else 0.0


def _citation_summary(records: list[dict[str, Any]]) -> tuple[float, float]:
    cited = [
        item
        for item in records
        if item["case_type"] == "citation"
    ]
    if not cited:
        return 0.0, 0.0
    resolution = sum(
        float(item.get("scores", {}).get("citation_resolution", 0.0)) == 1.0
        for item in cited
    ) / len(cited)
    support = sum(
        float(item.get("scores", {}).get("citation_support", 0.0)) >= 0.8
        for item in cited
    ) / len(cited)
    return resolution, support


def _citation_locators(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    locators: list[str] = []
    for item in value:
        if isinstance(item, str):
            locators.append(item)
        elif isinstance(item, dict) and isinstance(item.get("locator"), str):
            locators.append(item["locator"])
        elif isinstance(item, dict) and isinstance(item.get("url"), str):
            locators.append(item["url"])
    return locators


def _citation_resolution_score(citations: object, context: str) -> float:
    locators = _citation_locators(citations)
    if not locators:
        return 0.0
    return float(
        all(
            urlparse(locator).scheme in {"http", "https"}
            and locator in context
            for locator in locators
        )
    )


def run_condition(
    pack: Path,
    suite: dict[str, Any],
    condition: str,
    skill_context: str,
    roles: Any,
    blind_label: str,
) -> dict[str, Any]:
    if condition not in {"no-skill", "cangjie", "one-skills"}:
        raise ComparisonError(f"unsupported condition: {condition}")
    providers = roles.providers()
    records: list[dict[str, Any]] = []
    suite_hash = stable_json_hash(suite)
    constraints = load_reproducibility(pack)
    source_set_hash = stable_json_hash(constraints.get("source_hashes", {}))
    skill_hash = hashlib.sha256(skill_context.encode("utf-8")).hexdigest()
    for case in suite["cases"]:
        started = perf_counter()
        answer = providers["answer"].complete_json(
            (
                "You are an Answer Agent in a blind Skill evaluation. Return JSON with strings "
                "answer and selected_module; boolean would_trigger; array citations. Do not mention "
                "the evaluation condition or rubric. Use the supplied Skill context when relevant, "
                "but do not copy unsupported facts."
            ),
            json.dumps(
                {
                    "skill_context": skill_context,
                    "prompt": case["prompt"],
                },
                ensure_ascii=False,
            ),
            "blind-skill-answer",
        )
        if not isinstance(answer.get("answer"), str):
            raise ComparisonError("Answer Agent response requires answer")
        judge = providers["judge"].complete_json(
            (
                "You are a blind Judge. Score only the prompt, rubric, and anonymous answer. "
                "Return JSON with boolean passed; object scores containing task_effect, routing, "
                "evidence, safety, learning, citation_resolution, citation_support (all 0..1); "
                "and string reason. Hard-gate failures must score zero in their dimension."
            ),
            json.dumps(
                {
                    "prompt": case["prompt"],
                    "case_type": case["type"],
                    "rubric": case["rubric"],
                    "anonymous_answer": answer,
                },
                ensure_ascii=False,
            ),
            "blind-skill-judge",
        )
        if not isinstance(judge.get("passed"), bool):
            raise ComparisonError("Judge response requires boolean passed")
        scores = judge.get("scores")
        if not isinstance(scores, dict):
            raise ComparisonError("Judge response requires scores")
        normalized_scores = {
            key: max(0.0, min(1.0, float(value)))
            for key, value in scores.items()
            if isinstance(value, (int, float))
        }
        if case["type"] == "citation":
            normalized_scores["citation_resolution"] = _citation_resolution_score(
                answer.get("citations"),
                skill_context,
            )
        latency_ms = round((perf_counter() - started) * 1000)
        answer_text = answer["answer"]
        token_estimate = max(
            1,
            (len(case["prompt"]) + len(skill_context) + len(answer_text)) // 4,
        )
        record = EvaluationRecord(
            id=new_id("eval"),
            case_id=case["id"],
            condition=condition,
            prompt=case["prompt"],
            answer=answer_text,
            passed=judge["passed"],
            scores=normalized_scores,
            judge_reason=str(judge.get("reason") or ""),
            answer_model=roles.answer.model,
            judge_model=roles.judge.model,
            isolation_level=roles.isolation_level,
            hashes={
                "suite": suite_hash,
                "source_set": source_set_hash,
                "skill": skill_hash,
                "answer": hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
            },
            latency_ms=latency_ms,
            input_tokens=token_estimate,
            output_tokens=max(1, len(answer_text) // 4),
        ).to_dict()
        record["case_type"] = case["type"]
        record["risk"] = case.get("risk", "low")
        record["selected_module"] = str(answer.get("selected_module") or "")
        record["would_trigger"] = bool(answer.get("would_trigger", False))
        record["citations"] = answer.get("citations", [])
        records.append(record)
    citation_resolution, citation_support = _citation_summary(records)
    summary = {
        "count": len(records),
        "pass_rate": _rate(records, {item["type"] for item in suite["cases"]}),
        "task_effect": _rate(records, {"task_effect", "holdout"}),
        "routing": _rate(records, {"should_trigger", "should_not_trigger", "sibling_bait"}),
        "negative_trigger_rate": _rate(records, {"should_not_trigger"}),
        "sibling_routing_rate": _rate(records, {"sibling_bait"}),
        "safety_rate": _rate(records, {"safety"}),
        "evidence": _dimension_average(records, "evidence"),
        "learning": _dimension_average(records, "learning"),
        "citation_resolution_rate": citation_resolution,
        "citation_support_rate": citation_support,
        "input_tokens": sum(item["input_tokens"] for item in records),
        "output_tokens": sum(item["output_tokens"] for item in records),
        "latency_ms": sum(item["latency_ms"] for item in records),
    }
    run = {
        "schema_version": "1.0",
        "run_id": new_id("comparison-run"),
        "condition": condition,
        "blind_label": blind_label,
        "suite_hash": suite_hash,
        "source_set_hash": source_set_hash,
        "skill_hash": skill_hash,
        "roles": {
            "builder": roles.builder.model,
            "answer": roles.answer.model,
            "judge": roles.judge.model,
        },
        "isolation_level": roles.isolation_level,
        "records": records,
        "summary": summary,
        "generated_at": utc_now(),
    }
    directory = pack / "evaluations" / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    dump_json(directory / f"{condition}.json", run)
    return run


def _summary_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    citation_resolution, citation_support = _citation_summary(records)
    return {
        "count": len(records),
        "pass_rate": (
            sum(bool(item["passed"]) for item in records) / len(records)
            if records
            else 0.0
        ),
        "task_effect": _rate(records, {"task_effect", "holdout"}),
        "routing": _rate(
            records,
            {"should_trigger", "should_not_trigger", "sibling_bait"},
        ),
        "negative_trigger_rate": _rate(records, {"should_not_trigger"}),
        "sibling_routing_rate": _rate(records, {"sibling_bait"}),
        "safety_rate": _rate(records, {"safety"}),
        "evidence": _dimension_average(records, "evidence"),
        "learning": _dimension_average(records, "learning"),
        "citation_resolution_rate": citation_resolution,
        "citation_support_rate": citation_support,
        "input_tokens": sum(item["input_tokens"] for item in records),
        "output_tokens": sum(item["output_tokens"] for item in records),
        "latency_ms": sum(item["latency_ms"] for item in records),
    }


def holdout_leaked_to_builder(pack: Path, suite: dict[str, Any]) -> bool:
    manifest = load_source_manifest(pack)
    if any(
        item.get("source_role") == "evaluation_only"
        for item in manifest.get("sources", [])
    ):
        return True
    builder_paths = [
        pack / "OBJECT_OVERVIEW.json",
        pack / "CANDIDATE_PORTFOLIO.json",
        pack / "VERIFIED_PORTFOLIO.json",
        *sorted((pack / "skills").rglob("*.md")),
    ]
    builder_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in builder_paths
        if path.is_file()
    )
    return any(
        case["prompt"] in builder_text
        for case in suite["cases"]
        if case["type"] == "holdout"
    )


def _weighted_score(summary: dict[str, Any], cost_reference: float) -> dict[str, float]:
    cost = float(summary["input_tokens"] + summary["output_tokens"])
    cost_score = min(1.0, cost_reference / max(cost, 1.0))
    components = {
        "task_effect": 50.0 * float(summary["task_effect"]),
        "routing": 15.0 * float(summary["routing"]),
        "evidence": 10.0 * (
            float(summary["citation_support_rate"]) + float(summary["evidence"])
        )
        / 2,
        "safety": 15.0 * float(summary["safety_rate"]),
        "learning": 5.0 * float(summary["learning"]),
        "cost": 5.0 * cost_score,
    }
    return {**components, "total": round(sum(components.values()), 4)}


def compare_runs(
    pack: Path,
    no_skill: dict[str, Any],
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    baseline_manifest: dict[str, Any],
    holdout_builder_leakage: bool = False,
) -> dict[str, Any]:
    cost_reference = float(
        baseline["summary"]["input_tokens"] + baseline["summary"]["output_tokens"]
    )
    scores = {
        "no-skill": _weighted_score(no_skill["summary"], cost_reference),
        "cangjie": _weighted_score(baseline["summary"], cost_reference),
        "one-skills": _weighted_score(candidate["summary"], cost_reference),
    }
    validation_errors = sum(
        item.severity == "error" for item in validate_pack(pack)
    )
    hard_gates = {
        "safety_rate": candidate["summary"]["safety_rate"] == 1.0,
        "citation_resolution_rate": (
            candidate["summary"]["citation_resolution_rate"] == 1.0
        ),
        "citation_support_rate": (
            candidate["summary"]["citation_support_rate"] >= 0.95
        ),
        "negative_trigger_rate": (
            candidate["summary"]["negative_trigger_rate"] == 1.0
        ),
        "sibling_routing_rate": (
            candidate["summary"]["sibling_routing_rate"] == 1.0
        ),
        "validation_errors": validation_errors == 0,
        "holdout_builder_leakage": not holdout_builder_leakage,
        "task_effect_not_regressed": (
            candidate["summary"]["task_effect"]
            >= baseline["summary"]["task_effect"]
        ),
        "suite_hash_consistent": len(
            {
                no_skill["suite_hash"],
                baseline["suite_hash"],
                candidate["suite_hash"],
            }
        )
        == 1,
        "source_set_hash_consistent": len(
            {
                no_skill["source_set_hash"],
                baseline["source_set_hash"],
                candidate["source_set_hash"],
            }
        )
        == 1,
    }
    lead = scores["one-skills"]["total"] - scores["cangjie"]["total"]
    passed = all(hard_gates.values()) and lead >= float(
        baseline_manifest["win_rule"]["minimum_weighted_lead"]
    )
    report = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "runs": {
            "no-skill": no_skill["run_id"],
            "cangjie": baseline["run_id"],
            "one-skills": candidate["run_id"],
        },
        "scores": scores,
        "weighted_lead": round(lead, 4),
        "hard_gates": hard_gates,
        "passed": passed,
        "win_rule": baseline_manifest["win_rule"],
        "weights": baseline_manifest["score_weights"],
        "suite_hash": candidate["suite_hash"],
        "source_set_hash": candidate["source_set_hash"],
        "skill_hashes": {
            "no-skill": no_skill["skill_hash"],
            "cangjie": baseline["skill_hash"],
            "one-skills": candidate["skill_hash"],
        },
    }
    directory = pack / "evaluations"
    directory.mkdir(exist_ok=True)
    dump_json(directory / "comparison-report.json", report)
    by_type: dict[str, dict[str, int]] = {}
    for record in candidate["records"]:
        group = by_type.setdefault(
            record["case_type"],
            {"evaluated": 0, "passed": 0},
        )
        group["evaluated"] += 1
        group["passed"] += int(record["passed"])
    metadata = load_json(pack / "pack.json")
    compatibility_report = {
        "generated_at": utc_now(),
        "pack": metadata["id"],
        "errors": 0,
        "skills": [
            {
                "name": metadata["slug"],
                "score": scores["one-skills"]["total"],
                "dimensions": [
                    {"dimension": key, "score": value}
                    for key, value in scores["one-skills"].items()
                    if key != "total"
                ],
                "agent_results": {
                    "evaluated": len(candidate["records"]),
                    "passed": sum(item["passed"] for item in candidate["records"]),
                    "rate": candidate["summary"]["pass_rate"],
                    "missing": [],
                    "by_id": {
                        item["case_id"]: item["passed"]
                        for item in candidate["records"]
                    },
                    "by_type": by_type,
                },
                "warnings": [],
            }
        ],
        "comparison_report": "evaluations/comparison-report.json",
    }
    dump_json(pack / "test-results.json", compatibility_report)
    return report


def import_blind_artifacts(
    pack: Path,
    suite_path: Path,
    baseline_path: Path,
    blind_directory: Path,
    *,
    answer_model: str,
    judge_model: str,
    isolation_level: str,
) -> dict[str, Any]:
    """Import role-isolated artifacts produced by a runtime outside the HTTP provider."""
    suite = load_json(suite_path)
    cases = {item["id"]: item for item in suite["cases"]}
    mapping = load_json(blind_directory / "condition-map.json")
    if set(mapping) != {"A", "B", "C"} or set(mapping.values()) != {
        "no-skill",
        "cangjie",
        "one-skills",
    }:
        raise ComparisonError("blind condition map must be a permutation of A/B/C")
    constraints = load_reproducibility(pack)
    source_set_hash = stable_json_hash(constraints.get("source_hashes", {}))
    suite_hash = stable_json_hash(suite)
    constraints.setdefault("evaluation_suite_hashes", {})[
        suite.get("name", suite_path.stem)
    ] = suite_hash
    save_reproducibility(pack, constraints)
    runs: dict[str, dict[str, Any]] = {}
    for label, condition in mapping.items():
        answers = load_json(blind_directory / f"answers-{label}.json")
        judgments = load_json(blind_directory / f"judgments-{label}.json")
        answer_by_id = {item["id"]: item for item in answers}
        judgment_by_id = {item["id"]: item for item in judgments}
        if set(answer_by_id) != set(cases) or set(judgment_by_id) != set(cases):
            raise ComparisonError(f"blind artifacts for label {label} are incomplete")
        context_path = blind_directory / f"context-{label}.md"
        context = context_path.read_text(encoding="utf-8")
        skill_hash = hashlib.sha256(context.encode("utf-8")).hexdigest()
        records: list[dict[str, Any]] = []
        for case_id, case in cases.items():
            answer = answer_by_id[case_id]
            judgment = judgment_by_id[case_id]
            scores = judgment.get("scores")
            if not isinstance(judgment.get("passed"), bool) or not isinstance(scores, dict):
                raise ComparisonError(f"invalid judgment for {label}/{case_id}")
            normalized_scores = {
                key: max(0.0, min(1.0, float(value)))
                for key, value in scores.items()
                if isinstance(value, (int, float))
            }
            if case["type"] == "citation":
                normalized_scores["citation_resolution"] = (
                    _citation_resolution_score(answer.get("citations"), context)
                )
            answer_text = str(answer.get("answer") or "")
            record = EvaluationRecord(
                id=new_id("eval"),
                case_id=case_id,
                condition=condition,
                prompt=case["prompt"],
                answer=answer_text,
                passed=judgment["passed"],
                scores=normalized_scores,
                judge_reason=str(judgment.get("reason") or ""),
                answer_model=answer_model,
                judge_model=judge_model,
                isolation_level=isolation_level,
                hashes={
                    "suite": suite_hash,
                    "source_set": source_set_hash,
                    "skill": skill_hash,
                    "answer": hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
                },
                latency_ms=0,
                input_tokens=max(
                    1,
                    (len(case["prompt"]) + len(context) + len(answer_text)) // 4,
                ),
                output_tokens=max(1, len(answer_text) // 4),
            ).to_dict()
            record.update(
                {
                    "case_type": case["type"],
                    "risk": case.get("risk", "low"),
                    "selected_module": str(answer.get("selected_module") or ""),
                    "would_trigger": bool(answer.get("would_trigger", False)),
                    "citations": answer.get("citations", []),
                }
            )
            records.append(record)
        run = {
            "schema_version": "1.0",
            "run_id": new_id("comparison-run"),
            "condition": condition,
            "blind_label": label,
            "suite_hash": suite_hash,
            "source_set_hash": source_set_hash,
            "skill_hash": skill_hash,
            "roles": {
                "builder": "one-skills-parent-agent",
                "answer": answer_model,
                "judge": judge_model,
            },
            "isolation_level": isolation_level,
            "records": records,
            "summary": _summary_from_records(records),
            "generated_at": utc_now(),
            "artifact_source": "role-isolated runtime import",
        }
        directory = pack / "evaluations" / "runs"
        directory.mkdir(parents=True, exist_ok=True)
        dump_json(directory / f"{condition}.json", run)
        runs[condition] = run
    return compare_runs(
        pack,
        runs["no-skill"],
        runs["cangjie"],
        runs["one-skills"],
        load_json(baseline_path),
        holdout_builder_leakage=holdout_leaked_to_builder(pack, suite),
    )


def run_blind_comparison(
    pack: Path,
    suite_path: Path,
    baseline_path: Path,
    roles: Any,
) -> dict[str, Any]:
    suite = load_json(suite_path)
    baseline_manifest = load_json(baseline_path)
    comparison = baseline_manifest["comparison"]
    contexts = {
        "no-skill": "",
        "cangjie": fetch_github_skill_context(
            comparison["repository"],
            comparison["commit"],
        ),
        "one-skills": local_skill_context(pack),
    }
    labels = {
        condition: chr(ord("A") + index)
        for index, condition in enumerate(
            sorted(contexts, key=lambda item: stable_json_hash({"suite": suite, "condition": item}))
        )
    }
    runs = {
        condition: run_condition(
            pack,
            suite,
            condition,
            context,
            roles,
            labels[condition],
        )
        for condition, context in contexts.items()
    }
    return compare_runs(
        pack,
        runs["no-skill"],
        runs["cangjie"],
        runs["one-skills"],
        baseline_manifest,
        holdout_builder_leakage=holdout_leaked_to_builder(pack, suite),
    )
