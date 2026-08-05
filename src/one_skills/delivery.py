"""Validated installation, export, and Darwin handoff."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil

from .database import KnowledgeDB
from .evaluation import paired_decision
from .pipeline import advance_phase, load_state, workspace_for
from .reporting import write_evidence_graph
from .runtime import export_runtime
from .utils import atomic_write, dump_json, load_json, utc_now
from .validation import validate_pack


class DeliveryError(RuntimeError):
    pass


def _assert_tested(pack: Path) -> None:
    path = pack / "test-results.json"
    if not path.exists():
        raise DeliveryError("missing test-results.json")
    report = load_json(path)
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
    atomic_write(
        reports / "QUALITY.md",
        f"# Quality Report\n\n{quality_rows}\n\n"
        "Hard gates: safety, should-not-trigger, and sibling confusion all passed 100%.\n",
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
    atomic_write(
        pack / "DIGEST.md",
        "# Digest\n\n"
        + "\n".join(f"- [{skill['name']}](skills/{skill['name']}/SKILL.md)" for skill in skills)
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
