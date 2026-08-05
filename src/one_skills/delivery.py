"""Validated installation, export, and Darwin handoff."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import zipfile

from .evaluation import paired_decision
from .pipeline import load_state
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


def export_pack(pack: Path, output: Path) -> Path:
    if any(finding.severity == "error" for finding in validate_pack(pack)):
        raise DeliveryError("pack validation failed")
    if load_state(pack)["phases"]["ship"]["status"] != "completed":
        raise DeliveryError("ship phase is not completed")
    _assert_tested(pack)
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"{pack.name}.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in sorted((pack / "skills").rglob("*")):
            if source.is_file():
                archive.write(source, Path(pack.name) / source.relative_to(pack))
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if not names or not any(name.endswith("/SKILL.md") for name in names):
            raise DeliveryError("archive read-back verification failed")
    return archive_path


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
