"""Deterministic validation for Skills, evidence, tests, and Packs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .constants import EVIDENCE_TYPES, INFERENCE_LEVELS, PERMISSIONS, TEST_TYPES
from .core_assets import (
    load_recipe_lock,
    load_reproducibility,
    load_source_manifest,
    load_source_quality,
)
from .distillation_quality import assess_distillation_quality
from .errors import PipelineError
from .learning import validate_learning_path
from .lifecycle import load_state
from .provenance import source_set_fingerprint
from .schema_runtime import validate_schema
from .source_quality import source_quality_fingerprint
from .utils import load_json, stable_json_hash
from .versions import (
    CURRENT_PACK_VERSION,
    READABLE_PACK_VERSIONS,
    uses_consolidated_assets,
    uses_semantic_contract,
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _schema_findings(
    value: Any,
    schema_name: str,
    path: Path | str,
    code: str,
) -> list[Finding]:
    return [
        Finding(
            "error",
            code,
            f"{issue.path}: {issue.message}",
            str(path),
        )
        for issue in validate_schema(value, schema_name)
    ]


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    values: dict[str, str] = {}
    lines = text[4:end].splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line and line[0].isspace():
            index += 1
            continue
        if ":" not in line or line.lstrip().startswith("#"):
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value in {"|", ">"}:
            folded = value == ">"
            block: list[str] = []
            index += 1
            while index < len(lines):
                nested = lines[index]
                if nested and not nested[0].isspace():
                    break
                block.append(nested.strip())
                index += 1
            values[key] = (" " if folded else "\n").join(block).strip()
            continue
        if key == "metadata" and not value:
            nested_values: list[str] = []
            index += 1
            while index < len(lines):
                nested = lines[index]
                if nested and not nested[0].isspace():
                    break
                if nested.strip():
                    nested_values.append(nested.strip())
                index += 1
            values[key] = "\n".join(nested_values)
            continue
        values[key] = value.strip("\"'")
        index += 1
    return values, text[end + 5 :]


def validate_skill(skill_dir: Path) -> list[Finding]:
    path = skill_dir / "SKILL.md"
    if not path.exists():
        return [Finding("error", "skill.missing", "missing SKILL.md", str(path))]
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    findings: list[Finding] = []
    allowed_keys = {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
        "allowed-tools",
    }
    missing_keys = {"name", "description"} - set(metadata)
    extra_keys = set(metadata) - allowed_keys
    if missing_keys:
        findings.append(
            Finding(
                "error",
                "frontmatter.keys",
                f"frontmatter missing: {', '.join(sorted(missing_keys))}",
                str(path),
            )
        )
    if extra_keys:
        findings.append(
            Finding(
                "error",
                "frontmatter.keys",
                f"unsupported frontmatter keys: {', '.join(sorted(extra_keys))}",
                str(path),
            )
        )
    name = metadata.get("name", "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        findings.append(Finding("error", "frontmatter.name", "name must be <=64 character hyphen-case", str(path)))
    elif skill_dir.name != name:
        findings.append(
            Finding(
                "error",
                "frontmatter.directory_name",
                "name must match the parent directory",
                str(path),
            )
        )
    description = metadata.get("description", "")
    if not description or len(description) > 1024:
        findings.append(
            Finding(
                "error",
                "frontmatter.description",
                "description must contain 1-1024 characters",
                str(path),
            )
        )
    if not re.search(r"\b(use|when|for)\b|使用|当|适用于|触发", description, re.IGNORECASE):
        findings.append(Finding("warning", "frontmatter.trigger", "description may not encode a trigger", str(path)))
    compatibility = metadata.get("compatibility")
    if compatibility is not None and not 1 <= len(compatibility) <= 500:
        findings.append(
            Finding(
                "error",
                "frontmatter.compatibility",
                "compatibility must contain 1-500 characters",
                str(path),
            )
        )
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
    findings = _schema_findings(
        tests,
        "test-prompts.schema.json",
        path,
        "tests.schema",
    )
    if not isinstance(tests, list) or not tests:
        findings.append(
            Finding(
                "error",
                "tests.shape",
                "tests must be a non-empty array",
                str(path),
            )
        )
        return findings
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
        findings.extend(
            _schema_findings(
                item,
                "evidence.schema.json",
                f"{path}:{number}",
                "evidence.schema",
            )
        )
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
    constraints_path = pack / "pack.json"
    try:
        constraints = load_reproducibility(pack)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [
            Finding("error", "eval.constraints_parse", str(exc), str(constraints_path))
        ]
    if not isinstance(constraints, dict):
        return [
            Finding(
                "error",
                "eval.constraints_shape",
                "Pack reproducibility contract must be an object",
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
        findings.extend(
            _schema_findings(
                canonical,
                "canonical-evals.schema.json",
                canonical_path,
                "eval.canonical_schema",
            )
        )
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
        "recipe": pack / "pack.json",
        "constraints": pack / "pack.json",
        "manifest": pack / "SOURCE_MANIFEST.json",
    }
    if not paths["pack"].exists() or not paths["manifest"].exists():
        return []
    try:
        metadata = load_json(paths["pack"])
        recipe_lock = load_recipe_lock(pack)
        constraints = load_reproducibility(pack)
        manifest = load_source_manifest(pack)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
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
    pack_version = metadata.get("schema_version")
    if pack_version not in READABLE_PACK_VERSIONS:
        findings.append(
            Finding(
                "error",
                "pack.schema_version",
                "reproducible Packs require schema_version 0.2, 0.3, 0.4, or 1.0",
                str(paths["pack"]),
            )
        )
    if uses_semantic_contract(pack_version):
        semantic = metadata.get("semantic_contract")
        if (
            not isinstance(semantic, dict)
            or semantic.get("overview_confirmation")
            not in {"pending", "confirmed", "stale"}
            or semantic.get("capability_confirmation")
            not in {"pending", "confirmed", "stale"}
        ):
            findings.append(
                Finding(
                    "error",
                    "pack.semantic_contract",
                    "semantic Pack requires overview and capability confirmation states",
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
                "Pack recipe_lock is incomplete",
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
                "pack recipe identity does not match recipe_lock",
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
    if (
        pack_version == CURRENT_PACK_VERSION
        and constraints.get("source_set_hash")
        != source_set_fingerprint(manifest)
    ):
        findings.append(
            Finding(
                "error",
                "source.set_hash_drift",
                "source_set_hash does not match active and revoked Manifest state",
                str(paths["constraints"]),
            )
        )
    try:
        quality = load_source_quality(pack)
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(
            Finding(
                "error",
                "source.quality_parse",
                str(exc),
                str(paths["manifest"]),
            )
        )
        quality = {}
    if quality:
        if constraints.get("source_quality_hash") != source_quality_fingerprint(
            quality
        ):
            findings.append(
                Finding(
                    "error",
                    "source.quality_drift",
                    "source quality is not frozen or has drifted",
                    str(paths["manifest"]),
                )
            )
        if metadata.get("source_catalog") and quality.get("status") != "passed":
            findings.append(
                Finding(
                    "error",
                    "source.quality_gate",
                    "catalog-backed Pack did not pass its source quality gate",
                    str(paths["manifest"]),
                )
            )
    if uses_semantic_contract(pack_version):
        overview_path = pack / "OBJECT_OVERVIEW.json"
        if overview_path.exists():
            try:
                overview_hash = stable_json_hash(load_json(overview_path))
            except (OSError, json.JSONDecodeError) as exc:
                findings.append(
                    Finding(
                        "error",
                        "overview.parse",
                        str(exc),
                        str(overview_path),
                    )
                )
            else:
                if (
                    metadata.get("object_overview_hash") != overview_hash
                    or constraints.get("object_overview_hash") != overview_hash
                ):
                    findings.append(
                        Finding(
                            "error",
                            "overview.hash_drift",
                            "Object Overview is not frozen by Pack metadata and constraints",
                            str(overview_path),
                        )
                    )
        portfolio_path = pack / "VERIFIED_PORTFOLIO.json"
        if portfolio_path.exists():
            try:
                portfolio_hash = stable_json_hash(load_json(portfolio_path))
            except (OSError, json.JSONDecodeError) as exc:
                findings.append(
                    Finding(
                        "error",
                        "portfolio.parse",
                        str(exc),
                        str(portfolio_path),
                    )
                )
            else:
                if (
                    metadata.get("capability_portfolio_hash") != portfolio_hash
                    or constraints.get("capability_portfolio_hash")
                    != portfolio_hash
                ):
                    findings.append(
                        Finding(
                            "error",
                            "portfolio.hash_drift",
                            "Capability Portfolio is not frozen by Pack metadata and constraints",
                            str(portfolio_path),
                        )
                    )
        graph_path = pack / "CAPABILITY_GRAPH.json"
        if graph_path.exists():
            try:
                graph_hash = stable_json_hash(load_json(graph_path))
            except (OSError, json.JSONDecodeError) as exc:
                findings.append(
                    Finding(
                        "error",
                        "graph.parse",
                        str(exc),
                        str(graph_path),
                    )
                )
            else:
                if (
                    metadata.get("capability_graph_hash") != graph_hash
                    or constraints.get("capability_graph_hash") != graph_hash
                ):
                    findings.append(
                        Finding(
                            "error",
                            "graph.hash_drift",
                            "Capability Graph is not frozen by Pack metadata and constraints",
                            str(graph_path),
                        )
                    )
    return findings


def validate_pack(pack: Path) -> list[Finding]:
    findings: list[Finding] = []
    required = [
        "pack.json",
        "DISTILLATION_CONTRACT.md",
        "SOURCE_MANIFEST.json",
        "LEARNING_PATH.json",
        "EVIDENCE_LEDGER.jsonl",
        "INDEX.md",
    ]
    metadata: dict[str, Any] = {}
    metadata_path = pack / "pack.json"
    if metadata_path.exists():
        try:
            metadata = load_json(metadata_path)
            findings.extend(
                _schema_findings(
                    metadata,
                    "pack.schema.json",
                    metadata_path,
                    "pack.schema",
                )
            )
            version = metadata.get("schema_version")
            if not uses_consolidated_assets(version):
                required.extend(
                    (
                        "RECIPE_LOCK.json",
                        "PROTECTED_CONSTRAINTS.json",
                        "PIPELINE_STATE.json",
                        "SOURCE_QUALITY.json",
                        "OBJECT_MAP.md",
                    )
                )
            if uses_semantic_contract(version):
                overview_status = metadata.get("semantic_contract", {}).get(
                    "overview_confirmation"
                )
                if overview_status == "stale":
                    findings.append(
                        Finding(
                            "warning",
                            "semantic.rebuild_required",
                            "Object Overview is stale and must be rebuilt before release",
                            str(metadata_path),
                        )
                    )
                else:
                    required.extend(
                        ("OBJECT_OVERVIEW.json", "OBJECT_OVERVIEW.md")
                    )
                if metadata.get("capability_graph_hash"):
                    phase = load_state(pack).get("current_phase")
                    if phase in {"test", "ship", "evolve"}:
                        required.extend(
                            (
                                "CANDIDATE_PORTFOLIO.json",
                                "CANDIDATE_PORTFOLIO.md",
                                "VERIFIED_PORTFOLIO.json",
                                "VERIFIED_PORTFOLIO.md",
                                "CAPABILITY_GRAPH.json",
                                "GLOSSARY.md",
                                "DIGEST.md",
                            )
                        )
        except (OSError, PipelineError, json.JSONDecodeError):
            pass
    for relative in required:
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
        findings.append(Finding("error", "state.invalid", str(exc), str(pack / "pack.json")))

    schema_assets = [
        ("LEARNING_PATH.json", "learning-path.schema.json"),
        ("OBJECT_OVERVIEW.json", "object-overview.schema.json"),
        ("CANDIDATE_PORTFOLIO.json", "capability-portfolio.schema.json"),
        ("VERIFIED_PORTFOLIO.json", "capability-portfolio.schema.json"),
        ("CAPABILITY_GRAPH.json", "capability-graph.schema.json"),
        ("ir/distillation.json", "distillation-ir.schema.json"),
        (
            "evaluations/comparison-report.json",
            "comparison-report.schema.json",
        ),
        ("evaluations/suite.json", "comparison-suite.schema.json"),
    ]
    if uses_consolidated_assets(metadata.get("schema_version")):
        schema_assets.append(
            ("SOURCE_MANIFEST.json", "source-manifest.schema.json")
        )
    for relative, schema_name in schema_assets:
        path = pack / relative
        if not path.exists():
            continue
        try:
            value = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(
                Finding("error", "schema.parse", str(exc), str(path))
            )
            continue
        findings.extend(
            _schema_findings(
                value,
                schema_name,
                path,
                "schema.contract",
            )
        )
    for path in sorted((pack / "evaluations" / "runs").glob("*.json")):
        try:
            value = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(
                Finding("error", "schema.parse", str(exc), str(path))
            )
            continue
        findings.extend(
            _schema_findings(
                value,
                "evaluation-run.schema.json",
                path,
                "eval.run_schema",
            )
        )
    for path in sorted((pack / "evolution" / "proposals").glob("*.json")):
        try:
            value = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(
                Finding("error", "schema.parse", str(exc), str(path))
            )
            continue
        findings.extend(
            _schema_findings(
                value,
                "evolution-patch.schema.json",
                path,
                "evolution.patch_schema",
            )
        )
    findings.extend(validate_evidence(pack / "EVIDENCE_LEDGER.jsonl"))
    learning_path = pack / "LEARNING_PATH.json"
    if learning_path.exists():
        try:
            for error in validate_learning_path(load_json(learning_path)):
                findings.append(
                    Finding(
                        "error",
                        "learning.path",
                        error,
                        str(learning_path),
                    )
                )
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(
                Finding("error", "learning.parse", str(exc), str(learning_path))
            )
    findings.extend(validate_reproducibility(pack))
    findings.extend(validate_frozen_evals(pack))
    if (
        uses_consolidated_assets(metadata.get("schema_version"))
        and (pack / "CAPABILITY_GRAPH.json").exists()
    ):
        try:
            quality = assess_distillation_quality(pack)
            if quality["status"] == "failed":
                severity = (
                    "error"
                    if load_state(pack)["current_phase"] in {"ship", "evolve"}
                    else "warning"
                )
                failed = [
                    gate
                    for gate, passed in quality["hard_gates"].items()
                    if not passed
                ]
                findings.append(
                    Finding(
                        severity,
                        "distillation.quality_gate",
                        "failed core quality gates: " + ", ".join(failed),
                        str(pack / "pack.json"),
                    )
                )
        except (OSError, ValueError, json.JSONDecodeError, PipelineError) as exc:
            findings.append(
                Finding(
                    "error",
                    "distillation.quality_parse",
                    str(exc),
                    str(pack),
                )
            )
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
