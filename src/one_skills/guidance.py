"""Read-only CLI guidance derived from canonical Pack state."""

from __future__ import annotations

from ipaddress import ip_address
from pathlib import Path
import shlex
from typing import Any
from urllib.parse import urlparse

from .lifecycle import load_state
from .model_roles import model_status
from .utils import load_json


def _command(*parts: object) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def _network_scope(base_url: str) -> str:
    hostname = urlparse(base_url).hostname
    if not hostname:
        return "unknown"
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return "local"
    try:
        return "local" if ip_address(hostname).is_loopback else "remote"
    except ValueError:
        return "remote"


def _model_context() -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    try:
        status = model_status()
    except ValueError as exc:
        return (
            {"configured": False, "configuration_error": str(exc)},
            [],
            [f"Model role configuration is incomplete: {exc}"],
        )
    endpoints = [
        {
            "role": role,
            "base_url": str(config["base_url"]),
            "model": str(config["model"]),
            "network_scope": _network_scope(str(config["base_url"])),
        }
        for role, config in status.get("roles", {}).items()
    ]
    return status, endpoints, []


def _candidate_statuses(pack: Path) -> list[str]:
    decisions_path = pack / "verified" / "decisions.json"
    if not decisions_path.exists():
        return []
    decisions = load_json(decisions_path)
    return [
        str(item.get("status") or "")
        for item in decisions
        if isinstance(item, dict)
    ]


def _artifact_maturity(
    state: dict[str, Any],
    capability_confirmation: str,
    accepted_count: int,
) -> str:
    phases = state["phases"]
    if phases["ship"]["status"] == "completed":
        return "released"
    if phases["link"]["status"] == "completed":
        return "compiled_untested"
    if capability_confirmation == "confirmed":
        return "verified_confirmed"
    if accepted_count:
        return "verified_unconfirmed"
    return "draft_unverified"


def _result(
    state: dict[str, Any],
    maturity: str,
    action: str,
    *,
    command: str | None,
    blocked_by: list[str] | None = None,
    warnings: list[str] | None = None,
    endpoints: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    phase = state["current_phase"]
    return {
        "action": action,
        "phase": phase,
        "phase_status": state["phases"][phase]["status"],
        "artifact_maturity": maturity,
        "command": command,
        "blocked_by": blocked_by or [],
        "warnings": warnings or [],
        "endpoints": endpoints or [],
    }


def _sensitive_authorization(
    state: dict[str, Any],
    maturity: str,
    endpoints: list[dict[str, str]],
    purpose: str,
) -> dict[str, Any]:
    scope_warning = (
        "All configured endpoints are loopback destinations, but confirm that "
        "the local server does not proxy evidence externally."
        if endpoints
        and all(item["network_scope"] == "local" for item in endpoints)
        else "One or more configured model endpoints are remote."
    )
    return _result(
        state,
        maturity,
        "authorize_sensitive_data",
        command=None,
        blocked_by=["sensitive_data_authorization"],
        warnings=[
            scope_warning,
            f"Confirm that consent and the data agreement cover {purpose} at every "
            "listed endpoint, then rerun `one next` with "
            "`--allow-sensitive-data`.",
        ],
        endpoints=endpoints,
    )


def _comparison_action(
    state: dict[str, Any],
    maturity: str,
    metadata: dict[str, Any],
    pack: Path,
    frozen_suite: Path,
    baseline_path: Path | None,
    endpoints: list[dict[str, str]],
    *,
    allow_sensitive_data: bool,
    action: str = "run_comparison",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    if metadata.get("access_level") != "public" and not allow_sensitive_data:
        return _sensitive_authorization(
            state,
            maturity,
            endpoints,
            "sending the compiled Skill context for evaluation",
        )
    if baseline_path is None:
        return _result(
            state,
            maturity,
            action,
            command=None,
            blocked_by=["baseline_manifest_path"],
            warnings=(warnings or [])
            + [
                "Rerun `one next` with `--baseline <baseline.json>` to receive an "
                "executable comparison command."
            ],
            endpoints=endpoints,
        )
    baseline_path = baseline_path.expanduser().resolve()
    if not baseline_path.is_file():
        return _result(
            state,
            maturity,
            action,
            command=None,
            blocked_by=["baseline_manifest_file"],
            warnings=(warnings or [])
            + [f"Baseline manifest does not exist: {baseline_path}"],
            endpoints=endpoints,
        )
    command_parts: list[object] = [
        "one",
        "compare",
        "run",
        pack,
        "--suite",
        frozen_suite,
        "--baseline",
        baseline_path,
    ]
    if metadata.get("access_level") != "public":
        command_parts.append("--allow-sensitive-data")
    return _result(
        state,
        maturity,
        action,
        command=_command(*command_parts),
        warnings=warnings,
        endpoints=endpoints,
    )


def recommend_next_action(
    pack: Path,
    *,
    allow_sensitive_data: bool = False,
    suite_path: Path | None = None,
    baseline_path: Path | None = None,
    confirmation_notes: str | None = None,
) -> dict[str, Any]:
    """Return one next action without mutating the Pack or contacting providers."""
    pack = pack.expanduser().resolve()
    metadata = load_json(pack / "pack.json")
    state = load_state(pack)
    semantic = metadata.get("semantic_contract", {})
    overview_confirmation = str(semantic.get("overview_confirmation") or "")
    capability_confirmation = str(
        semantic.get("capability_confirmation") or ""
    )
    candidate_statuses = _candidate_statuses(pack)
    accepted_count = candidate_statuses.count("accepted")
    maturity = _artifact_maturity(
        state,
        capability_confirmation,
        accepted_count,
    )
    model, endpoints, model_warnings = _model_context()

    if overview_confirmation != "confirmed":
        warnings = [
            "This Pack is an unverified draft; stable release still requires "
            "role-separated verification and evaluation."
        ]
        if not model.get("configured"):
            warnings.append(
                "Model roles are not configured; run `one model status` before "
                "model verification."
            )
        if not confirmation_notes:
            warnings.append(
                "Review OBJECT_OVERVIEW.md, then rerun `one next` with "
                "`--notes <review notes>`."
            )
        return _result(
            state,
            maturity,
            "confirm_overview",
            command=(
                _command(
                    "one",
                    "semantic",
                    "confirm",
                    pack,
                    "--artifact",
                    "overview",
                    "--notes",
                    confirmation_notes,
                )
                if confirmation_notes
                else None
            ),
            blocked_by=(
                ["human_confirmation"]
                if confirmation_notes
                else ["human_confirmation", "confirmation_notes"]
            ),
            warnings=warnings,
        )

    if capability_confirmation != "confirmed":
        verification_audit = pack / "audit" / "model-verification.json"
        if accepted_count:
            warnings = [
                f"Review {pack / 'VERIFIED_PORTFOLIO.md'} before confirmation."
            ]
            if not confirmation_notes:
                warnings.append(
                    "Rerun `one next` with `--notes <review notes>` after review."
                )
            return _result(
                state,
                maturity,
                "confirm_portfolio",
                command=(
                    _command(
                        "one",
                        "semantic",
                        "confirm",
                        pack,
                        "--artifact",
                        "portfolio",
                        "--notes",
                        confirmation_notes,
                    )
                    if confirmation_notes
                    else None
                ),
                blocked_by=(
                    ["human_confirmation"]
                    if confirmation_notes
                    else ["human_confirmation", "confirmation_notes"]
                ),
                warnings=warnings,
            )
        pending_verification = bool(
            {"needs_model_verification", "needs_evidence"}
            & set(candidate_statuses)
        )
        if (
            verification_audit.exists()
            and candidate_statuses
            and not pending_verification
        ):
            return _result(
                state,
                maturity,
                "revise_unaccepted_candidates",
                command=_command("one", "inspect", pack),
                blocked_by=["no_accepted_candidates"],
                warnings=[
                    "Model verification accepted no candidates. Add evidence or "
                    "revise the source set before re-extraction."
                ],
            )
        if not model.get("configured"):
            return _result(
                state,
                maturity,
                "configure_model",
                command="one model status",
                blocked_by=["model_configuration"],
                warnings=model_warnings
                + [
                    "Configure Builder, Answer, and Judge roles before stable "
                    "verification."
                ],
            )
        if metadata.get("access_level") != "public" and not allow_sensitive_data:
            return _sensitive_authorization(
                state,
                maturity,
                endpoints,
                "sending source evidence for verification",
            )
        verify_parts: list[object] = ["one", "verify-model", pack]
        if metadata.get("access_level") != "public":
            verify_parts.append("--allow-sensitive-data")
        return _result(
            state,
            maturity,
            "verify_with_model",
            command=_command(*verify_parts),
            warnings=model_warnings,
            endpoints=endpoints,
        )

    if state["phases"]["link"]["status"] != "completed":
        return _result(
            state,
            maturity,
            "compile_portfolio",
            command=_command("one", "compile", pack),
        )

    if state["phases"]["ship"]["status"] == "completed":
        return _result(
            state,
            maturity,
            "install_or_export",
            command=_command("one", "install", pack, "--dry-run"),
            warnings=[
                "Review the dry-run, then install without `--dry-run`; use "
                "`one export` for a runtime archive."
            ],
        )

    frozen_suite = pack / "evaluations" / "suite.json"
    comparison_report = pack / "evaluations" / "comparison-report.json"
    if not frozen_suite.exists():
        if suite_path is None:
            return _result(
                state,
                maturity,
                "freeze_evaluation_suite",
                command=None,
                blocked_by=["evaluation_suite_path"],
                warnings=[
                    "Rerun `one next` with `--suite <suite.json>` to receive an "
                    "executable freeze command."
                ],
            )
        suite_path = suite_path.expanduser().resolve()
        if not suite_path.is_file():
            return _result(
                state,
                maturity,
                "freeze_evaluation_suite",
                command=None,
                blocked_by=["evaluation_suite_file"],
                warnings=[f"Evaluation suite does not exist: {suite_path}"],
            )
        return _result(
            state,
            maturity,
            "freeze_evaluation_suite",
            command=_command(
                "one",
                "compare",
                "freeze",
                pack,
                "--suite",
                suite_path,
            ),
        )

    report = load_json(comparison_report) if comparison_report.exists() else None
    if report and report.get("status") != "stale":
        if not report.get("passed"):
            return _result(
                state,
                maturity,
                "repair_failed_comparison",
                command=_command("one", "compare", "report", pack),
                blocked_by=["comparison_hard_gates"],
                warnings=[
                    "The frozen comparison failed. Inspect hard gates before "
                    "changing the Skill or evaluation inputs."
                ],
            )
        candidate_run_path = pack / "evaluations" / "runs" / "one-skills.json"
        candidate_run = (
            load_json(candidate_run_path) if candidate_run_path.exists() else {}
        )
        if report.get("isolation_level") not in {
            "provider-separated",
            "model-separated",
        } or candidate_run.get("artifact_source"):
            if model.get("isolation_level") in {
                "provider-separated",
                "model-separated",
            }:
                return _comparison_action(
                    state,
                    maturity,
                    metadata,
                    pack,
                    frozen_suite,
                    baseline_path,
                    endpoints,
                    allow_sensitive_data=allow_sensitive_data,
                    action="rerun_isolated_comparison",
                    warnings=[
                        "The previous result is not stable-release evidence; rerun "
                        "with the currently isolated roles."
                    ],
                )
            return _result(
                state,
                maturity,
                "rerun_isolated_comparison",
                command="one model status",
                blocked_by=["independent_model_roles"],
                warnings=[
                    "Stable release requires a directly executed comparison with "
                    "provider-separated or model-separated Answer and Judge roles."
                ],
                endpoints=endpoints,
            )
        return _result(
            state,
            maturity,
            "release_pack",
            command=_command("one", "release", pack),
        )

    stale_warnings = (
        [
            "The previous comparison is stale because authoritative Pack inputs "
            "changed."
        ]
        if report and report.get("status") == "stale"
        else []
    )
    if not model.get("configured"):
        return _result(
            state,
            maturity,
            "configure_model",
            command="one model status",
            blocked_by=["model_configuration"],
            warnings=model_warnings
            + stale_warnings
            + ["Role-separated models are required to run the frozen comparison."],
        )
    if model.get("isolation_level") not in {
        "provider-separated",
        "model-separated",
    }:
        return _result(
            state,
            maturity,
            "configure_independent_model_roles",
            command="one model status",
            blocked_by=["independent_model_roles"],
            warnings=stale_warnings
            + [
                "Stable comparison requires provider-separated or model-separated "
                "Answer and Judge roles."
            ],
            endpoints=endpoints,
        )
    return _comparison_action(
        state,
        maturity,
        metadata,
        pack,
        frozen_suite,
        baseline_path,
        endpoints,
        allow_sensitive_data=allow_sensitive_data,
        warnings=stale_warnings,
    )
