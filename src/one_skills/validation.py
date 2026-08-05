"""Deterministic validation for Skills, evidence, tests, and Packs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

from .constants import EVIDENCE_TYPES, INFERENCE_LEVELS, PERMISSIONS, TEST_TYPES
from .pipeline import load_state
from .utils import load_json


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values, text[end + 5 :]


def validate_skill(skill_dir: Path) -> list[Finding]:
    path = skill_dir / "SKILL.md"
    if not path.exists():
        return [Finding("error", "skill.missing", "missing SKILL.md", str(path))]
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    findings: list[Finding] = []
    if set(metadata) != {"name", "description"}:
        findings.append(
            Finding("error", "frontmatter.keys", "frontmatter must contain only name and description", str(path))
        )
    name = metadata.get("name", "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        findings.append(Finding("error", "frontmatter.name", "name must be <=64 character hyphen-case", str(path)))
    description = metadata.get("description", "")
    if len(description) < 40:
        findings.append(Finding("error", "frontmatter.description", "description must be at least 40 characters", str(path)))
    if not re.search(r"\b(use|when|for)\b|使用|当|适用于|触发", description, re.IGNORECASE):
        findings.append(Finding("warning", "frontmatter.trigger", "description may not encode a trigger", str(path)))
    requirements = {
        "workflow": r"工作流|workflow|步骤",
        "boundary": r"边界|boundary|不要|禁止",
        "failure": r"失败|failure|fallback|降级",
        "checkpoint": r"检查点|checkpoint|确认",
        "evidence": r"证据|evidence",
    }
    for code, pattern in requirements.items():
        if not re.search(pattern, body, re.IGNORECASE):
            findings.append(Finding("warning", f"skill.{code}", f"missing {code} section", str(path)))
    if len(body.splitlines()) > 500:
        findings.append(Finding("warning", "skill.length", "SKILL.md exceeds 500 lines", str(path)))
    canonical = skill_dir / "evals" / "canonical.json"
    if not canonical.exists():
        findings.append(
            Finding("warning", "skill.canonical_evals", "missing canonical evals", str(canonical))
        )
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", body):
        target = match.group(1).split("#", 1)[0]
        if not target or "://" in target or target.startswith("#"):
            continue
        if not (skill_dir / target).resolve().exists():
            findings.append(Finding("error", "skill.reference", f"missing reference: {target}", str(path)))
    return findings


def validate_tests(path: Path) -> list[Finding]:
    try:
        tests = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [Finding("error", "tests.parse", str(exc), str(path))]
    if not isinstance(tests, list) or not tests:
        return [Finding("error", "tests.shape", "tests must be a non-empty array", str(path))]
    findings: list[Finding] = []
    seen: set[str] = set()
    types: set[str] = set()
    for index, case in enumerate(tests):
        location = f"{path}#{index}"
        if not isinstance(case, dict):
            findings.append(Finding("error", "tests.case", "test must be an object", location))
            continue
        missing = {"id", "type", "prompt", "expected"} - set(case)
        if missing:
            findings.append(Finding("error", "tests.required", f"missing: {', '.join(sorted(missing))}", location))
        if case.get("id") in seen:
            findings.append(Finding("error", "tests.duplicate", f"duplicate id: {case.get('id')}", location))
        seen.add(case.get("id"))
        test_type = case.get("type")
        if test_type not in TEST_TYPES:
            findings.append(Finding("error", "tests.type", f"invalid type: {test_type}", location))
        else:
            types.add(test_type)
    for required in ("should_trigger", "should_not_trigger", "edge_case"):
        if required not in types:
            findings.append(Finding("error", "tests.coverage", f"missing {required}", str(path)))
    if "sibling_bait" not in types:
        findings.append(Finding("warning", "tests.sibling", "missing sibling confusion test", str(path)))
    return findings


def validate_evidence(path: Path) -> list[Finding]:
    if not path.exists():
        return [Finding("error", "evidence.missing", "missing evidence ledger", str(path))]
    findings: list[Finding] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            findings.append(Finding("error", "evidence.parse", str(exc), f"{path}:{number}"))
            continue
        required = {
            "id", "claim", "evidence_type", "source", "locator", "confidence",
            "inference_level", "permission",
        }
        missing = required - set(item)
        if missing:
            findings.append(Finding("error", "evidence.required", f"missing: {', '.join(sorted(missing))}", f"{path}:{number}"))
        if item.get("id") in seen:
            findings.append(Finding("error", "evidence.duplicate", f"duplicate id: {item.get('id')}", f"{path}:{number}"))
        seen.add(item.get("id"))
        if item.get("evidence_type") not in EVIDENCE_TYPES:
            findings.append(Finding("error", "evidence.type", "invalid evidence_type", f"{path}:{number}"))
        if item.get("inference_level") not in INFERENCE_LEVELS:
            findings.append(Finding("error", "evidence.inference", "invalid inference_level", f"{path}:{number}"))
        if item.get("permission") not in PERMISSIONS:
            findings.append(Finding("error", "evidence.permission", "invalid permission", f"{path}:{number}"))
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            findings.append(Finding("error", "evidence.confidence", "confidence must be in [0,1]", f"{path}:{number}"))
    return findings


def validate_pack(pack: Path) -> list[Finding]:
    findings: list[Finding] = []
    for relative in (
        "pack.json",
        "DISTILLATION_CONTRACT.md",
        "PIPELINE_STATE.json",
        "SOURCE_MANIFEST.json",
        "OBJECT_MAP.md",
        "EVIDENCE_LEDGER.jsonl",
        "INDEX.md",
    ):
        if not (pack / relative).exists():
            findings.append(Finding("error", "pack.missing", f"missing {relative}", str(pack / relative)))
    try:
        state = load_state(pack)
        if state["phases"]["link"]["status"] == "completed" and not (
            pack / "ir" / "distillation.json"
        ).exists():
            findings.append(
                Finding(
                    "error",
                    "ir.missing",
                    "linked Pack is missing canonical Distillation IR",
                    str(pack / "ir" / "distillation.json"),
                )
            )
        if state["phases"]["ship"]["status"] == "completed":
            for relative in (
                "MODEL_CARD.md",
                "DIGEST.md",
                "reports/QUALITY.md",
                "reports/PROVENANCE.md",
                "reports/EVIDENCE_GRAPH.md",
            ):
                if not (pack / relative).exists():
                    findings.append(
                        Finding("error", "release.missing", f"missing {relative}", str(pack / relative))
                    )
    except (PipelineError, OSError, json.JSONDecodeError) as exc:
        findings.append(Finding("error", "state.invalid", str(exc), str(pack / "PIPELINE_STATE.json")))
    findings.extend(validate_evidence(pack / "EVIDENCE_LEDGER.jsonl"))
    for skill_file in sorted((pack / "skills").glob("*/SKILL.md")):
        findings.extend(validate_skill(skill_file.parent))
        tests = skill_file.parent / "test-prompts.json"
        if not tests.exists():
            findings.append(Finding("error", "tests.missing", "missing test-prompts.json", str(tests)))
        else:
            findings.extend(validate_tests(tests))
    return findings


def summary(findings: list[Finding]) -> dict[str, Any]:
    return {
        "errors": sum(item.severity == "error" for item in findings),
        "warnings": sum(item.severity == "warning" for item in findings),
        "findings": [item.to_dict() for item in findings],
    }


from .pipeline import PipelineError
