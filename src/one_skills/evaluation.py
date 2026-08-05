"""Static diagnostics, independent result aggregation, and paired decisions."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .utils import atomic_write, dump_json, load_json, utc_now
from .validation import parse_frontmatter, validate_skill, validate_tests


@dataclass(frozen=True)
class Score:
    dimension: str
    weight: int
    score: int
    notes: str


def static_scores(skill_dir: Path) -> list[Score]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    findings = validate_skill(skill_dir)
    errors = Counter(item.code for item in findings if item.severity == "error")
    signals = {
        "workflow": body.count("\n1.") + body.count("\n2.") + body.count("\n3."),
        "failure_modes": sum(body.lower().count(term) for term in ("失败", "降级", "fallback")),
        "checkpoints": sum(body.lower().count(term) for term in ("检查点", "确认", "checkpoint")),
        "specificity": sum(body.count(term) for term in ("输入", "输出", "完成标准", "停止")),
        "blacklist": sum(body.count(term) for term in ("不要", "禁止", "不得", "边界")),
    }
    return [
        Score("frontmatter", 7, 7 if metadata and not errors else 0, "name, description, trigger"),
        Score("workflow", 12, min(12, 4 + signals["workflow"]), "numbered executable steps"),
        Score("failure_modes", 12, min(12, 2 + signals["failure_modes"] * 2), "failure and fallback coverage"),
        Score("checkpoints", 6, min(6, signals["checkpoints"] * 2), "human or machine checkpoints"),
        Score("specificity", 18, min(18, 4 + signals["specificity"] * 2), "input/output/done specificity"),
        Score("resources", 4, 4 if (skill_dir / "references").exists() else 0, "linked resources"),
        Score("architecture", 12, min(12, 4 + body.count("\n## ")), "progressive disclosure"),
        Score("actual_effect", 23, 0, "only independent execution results can fill this score"),
        Score("blacklist", 6, min(6, signals["blacklist"]), "boundaries and anti-patterns"),
    ]


def aggregate_results(path: Path, expected_ids: set[str]) -> tuple[dict[str, Any], list[str]]:
    values = load_json(path)
    if not isinstance(values, list):
        raise ValueError("agent result file must be an array")
    selected: dict[str, bool] = {}
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("passed"), bool):
            raise ValueError("each result must contain id and boolean passed")
        result_id = value.get("id")
        if result_id in expected_ids:
            if result_id in selected:
                raise ValueError(f"duplicate result id: {result_id}")
            selected[result_id] = value["passed"]
    missing = sorted(expected_ids - selected.keys())
    passed = sum(selected.values())
    evaluated = len(selected)
    return {
        "evaluated": evaluated,
        "passed": passed,
        "rate": passed / evaluated if evaluated else 0.0,
        "missing": missing,
    }, ([f"missing results: {', '.join(missing)}"] if missing else [])


def evaluate_pack(pack: Path, results_path: Path | None = None) -> dict[str, Any]:
    skills: list[dict[str, Any]] = []
    errors = 0
    for skill_file in sorted((pack / "skills").glob("*/SKILL.md")):
        skill_dir = skill_file.parent
        test_file = skill_dir / "test-prompts.json"
        test_findings = validate_tests(test_file)
        errors += sum(item.severity == "error" for item in test_findings)
        tests = load_json(test_file) if not test_findings else []
        scores = static_scores(skill_dir)
        result = None
        warnings: list[str] = []
        if results_path:
            result, warnings = aggregate_results(results_path, {item["id"] for item in tests})
            scores = [
                Score(item.dimension, item.weight, round(item.weight * result["rate"]), "independent agent results")
                if item.dimension == "actual_effect"
                else item
                for item in scores
            ]
        skills.append(
            {
                "name": skill_dir.name,
                "score": sum(item.score for item in scores),
                "dimensions": [asdict(item) for item in scores],
                "agent_results": result,
                "warnings": warnings,
            }
        )
    report = {"generated_at": utc_now(), "pack": str(pack), "errors": errors, "skills": skills}
    dump_json(pack / "test-results.json", report)
    lines = ["# Test Results", "", f"Generated: {report['generated_at']}", ""]
    for skill in skills:
        lines.extend([f"## {skill['name']}", "", f"- Score: {skill['score']}/100"])
        if skill["agent_results"]:
            result = skill["agent_results"]
            lines.append(f"- Independent results: {result['passed']}/{result['evaluated']} ({result['rate']:.1%})")
        lines.append("")
    atomic_write(pack / "test-results.md", "\n".join(lines))
    return report


def paired_decision(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    if len(comparisons) not in {3, 5}:
        raise ValueError("paired evaluation requires 3 or 5 judges")
    verdicts = [item.get("verdict") for item in comparisons]
    if any(value not in {"after", "before", "tie"} for value in verdicts):
        raise ValueError("verdict must be after, before, or tie")
    counts = Counter(verdicts)
    majority = len(comparisons) // 2 + 1
    if counts["before"] >= majority:
        decision = "revert"
    elif counts["after"] >= majority or counts["tie"] >= majority:
        decision = "keep"
    else:
        decision = "human-review"
    return {"judges": len(comparisons), "counts": dict(counts), "decision": decision}
