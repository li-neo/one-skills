"""Unified read-only control plane for guided sessions, Packs, and workspaces.

A single stable machine contract (``one status <path> --json``) replaces the
previous three recovery surfaces (``inspect`` / ``next`` / ``guide status``).
Harnesses branch on the stable fields below, never on Markdown or prose:

- ``asset_kind``: ``pack`` | ``guided_session`` | ``workspace``
- ``active_controller``: which controller owns the next move
- ``current_stage`` / ``stage_status``: recovery position
- ``ready_to_advance``: whether the current stage's deterministic gate passes
- ``allowed_actions``: action whitelist the harness may execute
- ``blocker_code`` / ``blocked_by``: stable code + human explanation
- ``recommended_action``: one priority action with command/path/instruction
- ``gate``: itemized per-phase checks for the current asset
- ``details``: the underlying canonical state
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import PHASES
from .errors import PipelineError
from .guidance import recommend_next_action
from .guided import _CHECKPOINT_BY_STAGE, SESSION_STAGES, load_session
from .lifecycle import load_state
from .utils import load_json

CONTROL_SCHEMA_VERSION = "1.0"


def _check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": identifier, "passed": bool(passed), "detail": detail}


def _text_ready(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _no_template_placeholders(path: Path) -> bool:
    if not _text_ready(path):
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    return not any(
        token in lowered for token in ("todo", "{{", "tbd", "占位", "待填")
    )


def _count_jsonl(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    )


def _skills(pack: Path) -> list[Path]:
    if not (pack / "skills").is_dir():
        return []
    return sorted((pack / "skills").glob("*/SKILL.md"))


def _pack_gate(pack: Path, state: dict[str, Any], metadata: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    semantic = metadata.get("semantic_contract", {})
    decisions = pack / "verified" / "decisions.json"
    accepted = 0
    if decisions.is_file():
        try:
            accepted = sum(
                1
                for item in load_json(decisions)
                if isinstance(item, dict) and item.get("status") == "accepted"
            )
        except ValueError:
            accepted = 0
    comparison = pack / "evaluations" / "comparison-report.json"
    comparison_valid = False
    if comparison.is_file():
        try:
            report = load_json(comparison)
            comparison_valid = (
                report.get("status") == "valid" and report.get("passed") is True
            )
        except ValueError:
            comparison_valid = False

    return {
        "contract": [
            _check("contract_file", _text_ready(pack / "DISTILLATION_CONTRACT.md"), "DISTILLATION_CONTRACT.md 存在且非空"),
            _check("contract_no_placeholders", _no_template_placeholders(pack / "DISTILLATION_CONTRACT.md"), "契约不含模板占位符"),
        ],
        "ingest": [
            _check("source_manifest", _text_ready(pack / "SOURCE_MANIFEST.json"), "SOURCE_MANIFEST.json 存在"),
        ],
        "map": [
            _check("object_overview_md", _text_ready(pack / "OBJECT_OVERVIEW.md"), "OBJECT_OVERVIEW.md 存在"),
            _check("overview_confirmed", str(semantic.get("overview_confirmation") or "") == "confirmed", "对象地图已显式确认"),
        ],
        "extract": [
            _check("evidence_ledger", _count_jsonl(pack / "EVIDENCE_LEDGER.jsonl") > 0, "EVIDENCE_LEDGER.jsonl 至少一条 Claim"),
        ],
        "verify": [
            _check("accepted_candidate", accepted > 0, "至少一个 accepted 候选能力"),
        ],
        "compile": [
            _check("compiled_skill", len(_skills(pack)) > 0, "skills/*/SKILL.md 至少一个"),
        ],
        "link": [
            _check("learning_path", _text_ready(pack / "LEARNING_PATH.json"), "LEARNING_PATH.json 存在"),
        ],
        "test": [
            _check("comparison_valid", comparison_valid, "evaluations/comparison-report.json 为 valid 且 passed"),
        ],
        "ship": [
            _check("model_card", _text_ready(pack / "MODEL_CARD.md"), "MODEL_CARD.md 存在"),
            _check("digest", _text_ready(pack / "DIGEST.md"), "DIGEST.md 存在"),
        ],
        "evolve": [
            _check("darwin_request", _text_ready(pack / "evolution" / "DARWIN_REQUEST.md"), "evolution/DARWIN_REQUEST.md 存在"),
        ],
    }


def _pack_status(pack: Path, **kwargs: Any) -> dict[str, Any]:
    metadata = load_json(pack / "pack.json")
    state = load_state(pack)
    phase = str(state.get("current_phase") or "contract")
    if phase not in PHASES:
        raise PipelineError(f"pipeline current_phase is invalid: {phase}")
    gate = _pack_gate(pack, state, metadata)
    current_gate = gate.get(phase, [])
    stage_status = str(state["phases"].get(phase, {}).get("status") or "pending")
    ready_to_advance = stage_status != "completed" and bool(current_gate) and all(
        item["passed"] for item in current_gate
    )
    recommendation = recommend_next_action(pack, **kwargs)
    recommended_command = recommendation.get("command")
    recommended_action: dict[str, Any] = {
        "id": recommendation.get("action"),
        "command": recommended_command,
        "path": str(pack),
        "instruction": (
            "; ".join(recommendation.get("warnings") or []) or None
        ),
        "blocked_by": recommendation.get("blocked_by") or [],
    }
    allowed = [
        "status",
        "inspect",
        "validate",
        "next",
        str(recommendation.get("action") or ""),
    ]
    if ready_to_advance:
        allowed.append("advance")
    allowed = sorted({item for item in allowed if item})
    blocker_code = (
        (recommendation.get("blocked_by") or [None])[0]
        if not ready_to_advance
        else None
    )
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "path": str(pack),
        "asset_kind": "pack",
        "active_controller": "pack",
        "current_stage": phase,
        "stage_status": stage_status,
        "ready_to_advance": ready_to_advance,
        "allowed_actions": allowed,
        "blocker_code": blocker_code,
        "blocked_by": recommendation.get("blocked_by") or [],
        "recommended_action": recommended_action,
        "gate": gate,
        "details": {
            "mode": metadata.get("mode"),
            "profile": metadata.get("profile"),
            "access_level": metadata.get("access_level"),
            "artifact_maturity": recommendation.get("artifact_maturity"),
            "endpoints": recommendation.get("endpoints") or [],
            "alternatives": recommendation.get("alternatives") or [],
        },
    }


def _guided_status(workspace: Path) -> dict[str, Any]:
    state = load_session(workspace)
    current = str(state.get("current_stage") or SESSION_STAGES[0])
    if current not in SESSION_STAGES:
        raise PipelineError(f"guided current_stage is invalid: {current}")
    stage_status = str(state["stages"].get(current, {}).get("status") or "pending")
    checkpoint = _CHECKPOINT_BY_STAGE.get(current)
    checkpoint_confirmed = (
        checkpoint is None
        or state["checkpoints"][checkpoint]["status"] == "confirmed"
    )
    # Mirror advance_session's stage-specific preconditions.
    if current == "discover":
        preconditions = bool(state.get("target_capability"))
        pre_errors = [] if preconditions else ["target_capability"]
    elif current == "interview":
        preconditions = _count_jsonl(workspace / "SESSION_EVENTS.jsonl") > 0
        pre_errors = [] if preconditions else ["session_events"]
    else:
        preconditions = True
        pre_errors = []
    ready_to_advance = (
        stage_status != "completed"
        and current != SESSION_STAGES[-1]
        and checkpoint_confirmed
        and preconditions
    )
    gate = {
        name: [
            _check(
                f"checkpoint_{name}",
                state["checkpoints"][name]["status"] == "confirmed",
                f"{name} 检查点已确认",
            )
        ]
        for name in state["checkpoints"]
    }
    gate["stage_preconditions"] = [
        _check("target_capability", bool(state.get("target_capability")), "已设定目标能力"),
        _check(
            "session_events",
            sum(state.get("evidence_counts", {}).values()) > 0
            or _count_jsonl(workspace / "SESSION_EVENTS.jsonl") > 0,
            "已记录证据或显式缺口",
        ),
    ]
    allowed = [
        "status",
        "guide",
        "guide-set",
        "guide-record",
        "guide-confirm",
        "guide-export",
    ]
    if ready_to_advance:
        allowed.append("guide-advance")
    blocker_code = (
        pre_errors[0]
        if pre_errors
        else f"checkpoint_{checkpoint}"
        if checkpoint and not checkpoint_confirmed
        else None
    )
    recommended = {
        "id": "guide-advance" if ready_to_advance else "guide-record",
        "command": (
            f"one guide advance {workspace}"
            if ready_to_advance
            else f"one guide record {workspace}"
        ),
        "path": str(workspace),
        "instruction": "先记录证据或确认检查点" if not ready_to_advance else "阶段门已通过，可推进",
        "blocked_by": pre_errors or ([] if checkpoint_confirmed else [f"checkpoint_{checkpoint}"]),
    }
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "path": str(workspace),
        "asset_kind": "guided_session",
        "active_controller": "guided",
        "current_stage": current,
        "stage_status": stage_status,
        "ready_to_advance": ready_to_advance,
        "allowed_actions": sorted(set(allowed)),
        "blocker_code": blocker_code,
        "blocked_by": recommended["blocked_by"],
        "recommended_action": recommended,
        "gate": gate,
        "details": {
            "session_id": state.get("session_id"),
            "subject": state.get("subject"),
            "object_type": state.get("object_type"),
            "recommended_profile": state.get("recommended_profile"),
            "next_questions": state.get("next_questions") or [],
            "evidence_counts": state.get("evidence_counts") or {},
            "pack_path": state.get("pack_path"),
        },
    }


def _workspace_status(workspace: Path) -> dict[str, Any]:
    packs_dir = workspace / "packs"
    packs = (
        sorted(p.name for p in packs_dir.iterdir() if (p / "pack.json").exists())
        if packs_dir.is_dir()
        else []
    )
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "path": str(workspace),
        "asset_kind": "workspace",
        "active_controller": "none",
        "current_stage": None,
        "stage_status": None,
        "ready_to_advance": False,
        "allowed_actions": ["status", "distill", "route", "source"],
        "blocker_code": None,
        "blocked_by": [],
        "recommended_action": {
            "id": "distill",
            "command": f"one distill --workspace {workspace}",
            "path": str(workspace),
            "instruction": "创建或选择一个 Pack 后运行 `one status <pack>`",
            "blocked_by": [],
        },
        "gate": {},
        "details": {"packs": packs},
    }


def build_control_status(
    path: Path,
    *,
    allow_sensitive_data: bool = False,
    suite_path: Path | None = None,
    baseline_path: Path | None = None,
    confirmation_notes: str | None = None,
) -> dict[str, Any]:
    """Return the unified control contract for a guided session, Pack, or workspace."""
    path = path.expanduser().resolve()
    if (path / "pack.json").is_file():
        return _pack_status(
            path,
            allow_sensitive_data=allow_sensitive_data,
            suite_path=suite_path,
            baseline_path=baseline_path,
            confirmation_notes=confirmation_notes,
        )
    if (path / "SESSION_STATE.json").is_file():
        return _guided_status(path)
    if (path / ".one" / "config.json").is_file():
        return _workspace_status(path)
    raise PipelineError(
        f"no one-skills asset at {path} (expected a Pack, guided session, or workspace)"
    )
