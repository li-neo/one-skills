"""Deterministic validation for Skills, evidence, tests, and Packs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

from .constants import EVIDENCE_TYPES, INFERENCE_LEVELS, PERMISSIONS, TEST_TYPES
from .pipeline import load_state
from .utils import load_json, stable_json_hash


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


def validate_frozen_evals(pack: Path) -> list[Finding]:
    constraints_path = pack / "PROTECTED_CONSTRAINTS.json"
    if not constraints_path.exists():
        return [
            Finding(
                "error",
                "eval.constraints_missing",
                "missing PROTECTED_CONSTRAINTS.json",
                str(constraints_path),
            )
        ]
    try:
        constraints = load_json(constraints_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [
            Finding("error", "eval.constraints_parse", str(exc), str(constraints_path))
        ]
    if not isinstance(constraints, dict):
        return [
            Finding(
                "error",
                "eval.constraints_shape",
                "PROTECTED_CONSTRAINTS.json must be an object",
                str(constraints_path),
            )
        ]
    canonical_hashes = constraints.get("canonical_eval_hashes", {})
    runtime_hashes = constraints.get("runtime_eval_hashes", {})
    if not isinstance(canonical_hashes, dict) or not isinstance(runtime_hashes, dict):
        return [
            Finding(
                "error",
                "eval.constraints_shape",
                "evaluation hash maps must be objects",
                str(constraints_path),
            )
        ]
    findings: list[Finding] = []
    for skill_file in sorted((pack / "skills").glob("*/SKILL.md")):
        skill = skill_file.parent
        canonical_path = skill / "evals" / "canonical.json"
        runtime_path = skill / "test-prompts.json"
        if not canonical_path.exists():
            findings.append(
                Finding(
                    "error",
                    "eval.canonical_missing",
                    "compiled Skill is missing canonical evaluations",
                    str(canonical_path),
                )
            )
            continue
        if not runtime_path.exists():
            findings.append(
                Finding(
                    "error",
                    "eval.runtime_missing",
                    "compiled Skill is missing runtime evaluations",
                    str(runtime_path),
                )
            )
            continue
        try:
            canonical = load_json(canonical_path)
            runtime = load_json(runtime_path)
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(
                Finding("error", "eval.parse", str(exc), str(skill))
            )
            continue
        name = skill.name
        required = {
            "schema_version",
            "suite_version",
            "skill",
            "profile",
            "protected_gates",
            "cases",
        }
        if not isinstance(canonical, dict) or not required <= set(canonical):
            findings.append(
                Finding(
                    "error",
                    "eval.canonical_shape",
                    "canonical suite is missing required fields",
                    str(canonical_path),
                )
            )
            continue
        if (
            canonical.get("schema_version") != "1.0"
            or not isinstance(canonical.get("suite_version"), str)
            or not canonical["suite_version"]
            or canonical.get("skill") != name
        ):
            findings.append(
                Finding(
                    "error",
                    "eval.canonical_identity",
                    "canonical suite version or Skill identity is invalid",
                    str(canonical_path),
                )
            )
        required_gates = {
            "authorization",
            "safety",
            "source_facts",
            "should_not_trigger",
            "sibling_bait",
        }
        gates = canonical["protected_gates"]
        if (
            not isinstance(gates, list)
            or any(not isinstance(gate, str) for gate in gates)
            or not required_gates <= set(gates)
        ):
            findings.append(
                Finding(
                    "error",
                    "eval.protected_gates",
                    "canonical suite is missing protected gates",
                    str(canonical_path),
                )
            )
        if canonical_hashes.get(name) != stable_json_hash(canonical):
            findings.append(
                Finding(
                    "error",
                    "eval.canonical_drift",
                    "canonical evaluations are not frozen or have drifted",
                    str(canonical_path),
                )
            )
        if runtime_hashes.get(name) != stable_json_hash(runtime):
            findings.append(
                Finding(
                    "error",
                    "eval.runtime_drift",
                    "runtime evaluations are not frozen or have drifted",
                    str(runtime_path),
                )
            )
        if canonical.get("cases") != runtime:
            findings.append(
                Finding(
                    "error",
                    "eval.adapter_drift",
                    "canonical cases and runtime tests differ",
                    str(runtime_path),
                )
            )
    return findings


def validate_reproducibility(pack: Path) -> list[Finding]:
    paths = {
        "pack": pack / "pack.json",
        "recipe": pack / "RECIPE_LOCK.json",
        "constraints": pack / "PROTECTED_CONSTRAINTS.json",
        "manifest": pack / "SOURCE_MANIFEST.json",
    }
    if any(not path.exists() for path in paths.values()):
        return []
    try:
        metadata = load_json(paths["pack"])
        recipe_lock = load_json(paths["recipe"])
        constraints = load_json(paths["constraints"])
        manifest = load_json(paths["manifest"])
    except (OSError, json.JSONDecodeError) as exc:
        return [
            Finding("error", "reproducibility.parse", str(exc), str(pack))
        ]
    if not all(
        isinstance(value, dict)
        for value in (metadata, recipe_lock, constraints, manifest)
    ):
        return [
            Finding(
                "error",
                "reproducibility.shape",
                "Pack reproducibility files must be JSON objects",
                str(pack),
            )
        ]
    findings: list[Finding] = []
    if metadata.get("schema_version") != "0.2":
        findings.append(
            Finding(
                "error",
                "pack.schema_version",
                "reproducible Packs require schema_version 0.2",
                str(paths["pack"]),
            )
        )
    recipe_value = recipe_lock.get("recipe", {})
    recipe = recipe_value if isinstance(recipe_value, dict) else {}
    recipe_fields = {
        "id",
        "version",
        "profile",
        "parser",
        "chunker",
        "extractors",
        "verifier",
        "builder",
    }
    if (
        recipe_lock.get("schema_version") != "1.0"
        or not isinstance(recipe_value, dict)
        or not recipe_fields <= set(recipe)
    ):
        findings.append(
            Finding(
                "error",
                "recipe.lock_shape",
                "RECIPE_LOCK.json is incomplete",
                str(paths["recipe"]),
            )
        )
    if metadata.get("recipe") != {
        "id": recipe.get("id"),
        "version": recipe.get("version"),
    }:
        findings.append(
            Finding(
                "error",
                "recipe.lock_mismatch",
                "pack recipe identity does not match RECIPE_LOCK.json",
                str(paths["recipe"]),
            )
        )
    if recipe.get("profile") != metadata.get("profile"):
        findings.append(
            Finding(
                "error",
                "recipe.profile_mismatch",
                "locked Recipe profile does not match the Pack",
                str(paths["recipe"]),
            )
        )
    sources = manifest.get("sources", [])
    if not isinstance(sources, list) or any(
        not isinstance(item, dict)
        or not {"source_id", "document_version", "content_hash"} <= set(item)
        for item in sources
    ):
        findings.append(
            Finding(
                "error",
                "source.manifest_shape",
                "SOURCE_MANIFEST.json has invalid source records",
                str(paths["manifest"]),
            )
        )
        return findings
    expected_hashes = {
        f"{item['source_id']}@{item['document_version']}": item["content_hash"]
        for item in sources
    }
    if constraints.get("source_hashes") != expected_hashes:
        findings.append(
            Finding(
                "error",
                "source.hash_drift",
                "protected source hashes do not match SOURCE_MANIFEST.json",
                str(paths["constraints"]),
            )
        )
    return findings


def validate_pack(pack: Path) -> list[Finding]:
    findings: list[Finding] = []
    for relative in (
        "pack.json",
        "RECIPE_LOCK.json",
        "PROTECTED_CONSTRAINTS.json",
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
    findings.extend(validate_reproducibility(pack))
    findings.extend(validate_frozen_evals(pack))
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
