"""Validated installation, export, and Darwin handoff."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from .comparison import (
    COMPARISON_WEIGHTS,
    COMPARISON_WIN_RULE,
    calculate_comparison,
    holdout_leaked_to_builder,
    judge_artifact_hash,
    local_skill_context,
)
from .core_assets import load_reproducibility
from .database import KnowledgeDB
from .distillation_quality import assess_distillation_quality
from .evaluation import paired_decision
from .lifecycle import advance_phase, load_state, workspace_for
from .provenance import current_source_set_hash
from .reporting import write_evidence_graph
from .runtime import export_runtime
from .utils import atomic_write, dump_json, load_json, stable_json_hash, utc_now
from .validation import validate_frozen_evals, validate_pack
from .versions import uses_consolidated_assets, uses_semantic_contract


class DeliveryError(RuntimeError):
    pass


INDEPENDENT_ISOLATION_LEVELS = {"provider-separated", "model-separated"}


def _assert_no_pending_revocations(pack: Path) -> None:
    workspace = workspace_for(pack)
    directory = workspace / ".one" / "revocations"
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.json")):
        intent = load_json(path)
        if (
            intent.get("status") == "pending"
            and pack.name in intent.get("affected_packs", [])
        ):
            raise DeliveryError(
                f"pending source revocation blocks delivery: {intent.get('id')}"
            )


def _load_bound_evaluation_run(
    pack: Path,
    condition: str,
    comparison: dict,
    source_set_hash: str,
    suite_hash: str,
) -> dict:
    run_path = pack / "evaluations" / "runs" / f"{condition}.json"
    if not run_path.exists():
        raise DeliveryError(f"{condition} evaluation run is missing")
    run = load_json(run_path)
    if run.get("run_id") != comparison.get("runs", {}).get(condition):
        raise DeliveryError(f"{condition} evaluation run identity does not match report")
    if run.get("artifact_hash") != comparison.get("run_hashes", {}).get(condition):
        raise DeliveryError(f"{condition} evaluation run hash does not match report")
    artifact = dict(run)
    artifact_hash = artifact.pop("artifact_hash", None)
    if artifact_hash != stable_json_hash(artifact):
        raise DeliveryError(f"{condition} evaluation run artifact hash is invalid")
    skill_hash = run.get("skill_hash")
    if (
        run.get("suite_hash") != suite_hash
        or run.get("source_set_hash") != source_set_hash
        or run.get("input_snapshot_hash")
        != stable_json_hash(
            {
                "suite": suite_hash,
                "source_set": source_set_hash,
                "skill": skill_hash,
            }
        )
    ):
        raise DeliveryError(f"{condition} evaluation run hashes are stale")
    roles = run.get("roles", {})
    isolation = run.get("isolation_level")
    for record in run.get("records", []):
        hashes = record.get("hashes", {})
        if (
            hashes.get("suite") != suite_hash
            or hashes.get("source_set") != source_set_hash
            or hashes.get("skill") != skill_hash
            or hashes.get("answer")
            != hashlib.sha256(record.get("answer", "").encode("utf-8")).hexdigest()
            or hashes.get("judge")
            != judge_artifact_hash(
                bool(record.get("passed")),
                record.get("scores", {}),
                str(record.get("judge_reason") or ""),
            )
        ):
            raise DeliveryError(
                f"evaluation record hash is invalid: {condition}/{record.get('case_id')}"
            )
        if (
            record.get("answer_model") != roles.get("answer")
            or record.get("judge_model") != roles.get("judge")
            or record.get("isolation_level") != isolation
        ):
            raise DeliveryError(
                f"evaluation record role identity is invalid: "
                f"{condition}/{record.get('case_id')}"
            )
    return run


def _assert_tested(pack: Path) -> None:
    drift = [
        finding
        for finding in validate_frozen_evals(pack)
        if finding.severity == "error"
    ]
    if drift:
        raise DeliveryError(f"evaluation freeze check failed: {drift[0].code}")
    metadata = load_json(pack / "pack.json") if (pack / "pack.json").exists() else {}
    if (
        uses_semantic_contract(metadata.get("schema_version"))
        and (pack / "CAPABILITY_GRAPH.json").exists()
    ):
        comparison_path = pack / "evaluations" / "comparison-report.json"
        if not comparison_path.exists():
            raise DeliveryError("v0.3 release requires a blind comparison report")
        comparison = load_json(comparison_path)
        if comparison.get("status") != "valid":
            raise DeliveryError("blind comparison report is stale")
        if not comparison.get("passed"):
            raise DeliveryError(
                "blind comparison or a non-compensating hard gate failed"
            )
        constraints = load_reproducibility(pack)
        source_set_hash = current_source_set_hash(pack)
        if comparison.get("source_set_hash") != source_set_hash:
            raise DeliveryError(
                "blind comparison report does not match the current Source Set"
            )
        suite_hash = comparison.get("suite_hash")
        if suite_hash not in set(
            constraints.get("evaluation_suite_hashes", {}).values()
        ):
            raise DeliveryError(
                "blind comparison suite is not frozen by Pack reproducibility"
            )
        expected_skill_hash = comparison.get("skill_hashes", {}).get("one-skills")
        current_skill_hash = hashlib.sha256(
            local_skill_context(pack).encode("utf-8")
        ).hexdigest()
        if expected_skill_hash != current_skill_hash:
            raise DeliveryError(
                "blind comparison report does not match the current Skill context"
            )
        runs = {
            condition: _load_bound_evaluation_run(
                pack,
                condition,
                comparison,
                source_set_hash,
                suite_hash,
            )
            for condition in ("no-skill", "cangjie", "one-skills")
        }
        suite_path = pack / "evaluations" / "suite.json"
        if not suite_path.exists():
            raise DeliveryError("frozen comparison suite snapshot is missing")
        suite = load_json(suite_path)
        if stable_json_hash(suite) != suite_hash:
            raise DeliveryError("frozen comparison suite snapshot is stale")
        decision = calculate_comparison(
            pack,
            runs["no-skill"],
            runs["cangjie"],
            runs["one-skills"],
            holdout_leaked_to_builder(pack, suite),
        )
        if (
            comparison.get("scores") != decision["scores"]
            or comparison.get("weighted_lead")
            != decision["weighted_lead"]
            or comparison.get("hard_gates") != decision["hard_gates"]
            or comparison.get("passed") != decision["passed"]
            or comparison.get("weights") != COMPARISON_WEIGHTS
            or comparison.get("win_rule") != COMPARISON_WIN_RULE
        ):
            raise DeliveryError(
                "blind comparison conclusion does not match bound evaluation runs"
            )
        run = runs["one-skills"]
        if run.get("artifact_hash") != comparison.get("candidate_run_hash"):
            raise DeliveryError("candidate evaluation run hash does not match report")
        if run.get("artifact_source"):
            raise DeliveryError(
                "stable release requires directly executed evaluation; "
                "imported artifacts need a trusted runner signature"
            )
        isolation = run.get("isolation_level")
        if isolation not in INDEPENDENT_ISOLATION_LEVELS:
            raise DeliveryError(
                "stable release requires provider-separated or model-separated evaluation"
            )
        roles = run.get("roles", {})
        if (
            isolation == "model-separated"
            and roles.get("answer") == roles.get("judge")
        ):
            raise DeliveryError(
                "model-separated evaluation requires different Answer and Judge models"
            )
        if (
            run.get("skill_hash") != current_skill_hash
            or comparison.get("isolation_level") != isolation
        ):
            raise DeliveryError("candidate evaluation run hashes are stale")
    if (
        uses_consolidated_assets(metadata.get("schema_version"))
        and (pack / "CAPABILITY_GRAPH.json").exists()
    ):
        quality = assess_distillation_quality(pack)
        if not quality["passed"]:
            failed = [
                gate
                for gate, passed in quality["hard_gates"].items()
                if not passed
            ]
            raise DeliveryError(
                "core distillation quality gates failed: " + ", ".join(failed)
            )
    path = pack / "test-results.json"
    if not path.exists():
        raise DeliveryError("missing test-results.json")
    report = load_json(path)
    if report.get("status") != "valid":
        raise DeliveryError("independent test results are not valid")
    if report.get("errors") or not report.get("skills"):
        raise DeliveryError("test report is incomplete or contains structural errors")
    for skill in report["skills"]:
        result = skill.get("agent_results")
        if not result or not result["evaluated"] or result["missing"]:
            raise DeliveryError(f"{skill['name']} lacks complete independent results")
        if result["rate"] < 0.8:
            raise DeliveryError(f"{skill['name']} independent pass rate is below 80%")
        by_type = result.get("by_type", {})
        for hard_gate in ("should_not_trigger", "sibling_bait", "safety"):
            group = by_type.get(hard_gate)
            if not group or group["evaluated"] == 0 or group["passed"] != group["evaluated"]:
                raise DeliveryError(f"{skill['name']} did not fully pass hard gate {hard_gate}")


def release_pack(pack: Path) -> dict:
    """Close test and ship phases only after all non-negotiable gates pass."""
    _assert_no_pending_revocations(pack)
    findings = validate_pack(pack)
    errors = [finding for finding in findings if finding.severity == "error"]
    if errors:
        raise DeliveryError(f"pack has {len(errors)} validation errors")
    _assert_tested(pack)
    state = load_state(pack)
    if state["current_phase"] != "test":
        raise DeliveryError(f"release requires current phase test, got {state['current_phase']}")
    advance_phase(pack, "test", "completed", "independent tests and hard gates passed")
    report = load_json(pack / "test-results.json")
    metadata = load_json(pack / "pack.json")
    reports = pack / "reports"
    reports.mkdir(exist_ok=True)
    skills = report["skills"]
    quality_rows = "\n".join(
        f"- `{skill['name']}`: {skill['score']}/100, "
        f"independent pass {skill['agent_results']['rate']:.1%}"
        for skill in skills
    )
    comparison_path = pack / "evaluations" / "comparison-report.json"
    comparison_text = ""
    if comparison_path.exists():
        comparison = load_json(comparison_path)
        comparison_text = (
            f"\n- Weighted lead over baseline: {comparison.get('weighted_lead', 0):.2f}\n"
            f"- Comparison passed: `{comparison.get('passed', False)}`\n"
        )
    core_quality_text = ""
    if uses_consolidated_assets(metadata.get("schema_version")):
        core_quality = assess_distillation_quality(pack)
        dimensions = core_quality["dimensions"]
        core_quality_text = (
            "\n- Distillation reliability: "
            f"{dimensions['reliability']:.4f}\n"
            f"- Distillation completeness: {dimensions['completeness']:.4f}\n"
            f"- Distillation accuracy: {dimensions['accuracy']:.4f}\n"
        )
    atomic_write(
        reports / "QUALITY.md",
        f"# Quality Report\n\n{quality_rows}\n\n"
        "Hard gates: safety, should-not-trigger, sibling confusion, citations, "
        "hash consistency, and holdout isolation passed.\n"
        + comparison_text
        + core_quality_text,
    )
    atomic_write(
        reports / "PROVENANCE.md",
        f"# Provenance\n\n- Pack: `{metadata['id']}`\n"
        f"- Profile: `{metadata['profile']}`\n"
        f"- Created: {metadata['created_at']}\n"
        "- Evidence: `../EVIDENCE_LEDGER.jsonl`\n"
        "- Sources: `../SOURCE_MANIFEST.json`\n",
    )
    atomic_write(
        pack / "MODEL_CARD.md",
        f"# Model Card\n\n- Status: `ready`\n- Profile: `{metadata['profile']}`\n"
        "- Known limitation: semantic claims are bounded by captured sources and verification time.\n"
        "- Revocation: remove or revoke the source, then rebuild affected lineage.\n",
    )
    if not (pack / "DIGEST.md").exists():
        atomic_write(
            pack / "DIGEST.md",
            "# Digest\n\n"
            + "\n".join(
                f"- [{skill['name']}](skills/{skill['name']}/SKILL.md)"
                for skill in skills
            )
            + "\n",
        )
    workspace = workspace_for(pack)
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        graph_path = write_evidence_graph(pack, database)
    advance_phase(pack, "ship", "completed", "reports generated and release gate passed")
    return {
        "status": "released",
        "skills": len(skills),
        "quality_report": str(reports / "QUALITY.md"),
        "evidence_graph": str(graph_path),
        "current_phase": load_state(pack)["current_phase"],
    }


def default_target() -> Path:
    root = os.getenv("CODEX_HOME")
    return (Path(root).expanduser() if root else Path.home() / ".codex") / "skills"


def install_pack(
    pack: Path,
    target: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> list[dict[str, str]]:
    _assert_no_pending_revocations(pack)
    errors = [finding for finding in validate_pack(pack) if finding.severity == "error"]
    if errors:
        raise DeliveryError(f"pack has {len(errors)} validation errors")
    state = load_state(pack)
    if not dry_run and state["phases"]["ship"]["status"] != "completed":
        raise DeliveryError("ship phase is not completed")
    if not dry_run:
        _assert_tested(pack)
    destination_root = (target or default_target()).expanduser().resolve()
    actions: list[dict[str, str]] = []
    for source in sorted(path.parent for path in (pack / "skills").glob("*/SKILL.md")):
        destination = destination_root / source.name
        if destination.exists() and not force:
            raise DeliveryError(f"target exists: {destination}; use --force to back up and replace")
        action = {"source": str(source), "destination": str(destination), "action": "replace" if destination.exists() else "create"}
        actions.append(action)
        if dry_run:
            continue
        destination_root.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup = destination.with_name(f"{destination.name}.backup-{stamp}")
            destination.rename(backup)
            action["backup"] = str(backup)
        shutil.copytree(source, destination)
        if not (destination / "SKILL.md").is_file():
            raise DeliveryError(f"read-back verification failed: {destination}")
    return actions


def export_pack(pack: Path, output: Path, runtime: str = "generic") -> Path:
    _assert_no_pending_revocations(pack)
    if any(finding.severity == "error" for finding in validate_pack(pack)):
        raise DeliveryError("pack validation failed")
    if load_state(pack)["phases"]["ship"]["status"] != "completed":
        raise DeliveryError("ship phase is not completed")
    _assert_tested(pack)
    try:
        return export_runtime(pack, output, runtime)
    except ValueError as exc:
        raise DeliveryError(str(exc)) from exc


def prepare_darwin(
    pack: Path,
    skill_name: str | None = None,
    comparisons_path: Path | None = None,
) -> dict:
    _assert_tested(pack)
    skills = sorted(path.parent for path in (pack / "skills").glob("*/SKILL.md"))
    if skill_name:
        skills = [skill for skill in skills if skill.name == skill_name]
    if not skills:
        raise DeliveryError("no matching Skill")
    targets = []
    for skill in skills:
        tests = skill / "test-prompts.json"
        if not tests.exists():
            raise DeliveryError(f"missing Darwin tests: {tests}")
        targets.append({"skill": str(skill / "SKILL.md"), "tests": str(tests)})
    request = {
        "generated_at": utc_now(),
        "engine": "darwin-skill",
        "status": "prepared",
        "targets": targets,
        "protected": ["evidence", "permission", "safety", "negative_tests", "core_purpose"],
        "comparison": {"judges": 3, "method": "paired-same-judge"},
    }
    if comparisons_path:
        comparisons = json.loads(comparisons_path.read_text(encoding="utf-8"))
        request["paired_result"] = paired_decision(comparisons)
    evolution = pack / "evolution"
    evolution.mkdir(exist_ok=True)
    dump_json(evolution / "darwin-request.json", request)
    lines = ["# Darwin Request", "", "状态：`prepared`。此文件不表示 Darwin 已执行。", ""]
    for target in targets:
        lines.append(f"- `{target['skill']}` with `{target['tests']}`")
    lines.extend(["", "冻结证据、权限、安全、反触发和核心用途；退化时回滚。", ""])
    atomic_write(evolution / "DARWIN_REQUEST.md", "\n".join(lines))
    return request
