"""Pack lifecycle state machine and workspace ownership."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import MODES, PHASE_INDEX, PHASES
from .core_assets import (
    CONSOLIDATED_PACK_VERSION,
    load_pack_metadata,
    save_pack_metadata,
)
from .database import KnowledgeDB
from .errors import PipelineError
from .recipes import initialize_registry
from .utils import dump_json, load_json, utc_now


def init_workspace(path: Path, mode: str = "standard") -> Path:
    if mode not in MODES:
        raise PipelineError(f"unsupported mode: {mode}")
    root = path.expanduser().resolve()
    for relative in (
        "guided",
        "packs",
        "dist",
        "knowledge/sources",
        "knowledge/normalized",
        ".one",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    dump_json(
        root / ".one" / "config.json",
        {
            "schema_version": "0.1",
            "default_mode": mode,
            "database": ".one/knowledge.db",
            "packs_dir": "packs",
            "dist_dir": "dist",
        },
    )
    with KnowledgeDB(root / ".one" / "knowledge.db"):
        pass
    initialize_registry(root / ".one" / "recipes.json")
    return root


def workspace_for(path: Path) -> Path:
    current = path.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".one" / "config.json").exists():
            return candidate
    raise PipelineError(f"no one-skills workspace found from {path}")


def new_lifecycle(pack_id: str) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": "1.0",
        "pack_id": pack_id,
        "current_phase": "contract",
        "created_at": now,
        "updated_at": now,
        "phases": {
            phase: {
                "status": "in_progress" if phase == "contract" else "pending",
                "updated_at": now if phase == "contract" else None,
                "notes": "",
            }
            for phase in PHASES
        },
    }


def save_state(pack: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    metadata_path = pack / "pack.json"
    if metadata_path.exists():
        metadata = load_pack_metadata(pack)
        if metadata.get("schema_version") == CONSOLIDATED_PACK_VERSION:
            metadata["lifecycle"] = state
            save_pack_metadata(pack, metadata)
            return
    dump_json(pack / "PIPELINE_STATE.json", state)


def load_state(pack: Path) -> dict[str, Any]:
    metadata_path = pack / "pack.json"
    if metadata_path.exists():
        metadata = load_pack_metadata(pack)
        if metadata.get("schema_version") == CONSOLIDATED_PACK_VERSION:
            state = metadata.get("lifecycle")
            if not isinstance(state, dict):
                raise PipelineError("consolidated Pack is missing lifecycle")
            if state.get("current_phase") not in PHASES:
                raise PipelineError("pipeline current_phase is invalid")
            return state
    path = pack / "PIPELINE_STATE.json"
    if not path.exists():
        raise PipelineError(f"invalid pack; missing {path}")
    state = load_json(path)
    if state.get("current_phase") not in PHASES:
        raise PipelineError("pipeline current_phase is invalid")
    return state


def advance_phase(
    pack: Path,
    phase: str,
    status: str,
    notes: str = "",
) -> dict[str, Any]:
    if phase not in PHASES:
        raise PipelineError(f"unknown phase: {phase}")
    if status not in {"pending", "in_progress", "completed", "blocked"}:
        raise PipelineError(f"unknown phase status: {status}")
    state = load_state(pack)
    if status == "completed":
        unfinished = [
            previous
            for previous in PHASES[: PHASE_INDEX[phase]]
            if state["phases"][previous]["status"] != "completed"
        ]
        if unfinished:
            raise PipelineError(
                f"cannot skip unfinished phases: {', '.join(unfinished)}"
            )
    state["phases"][phase] = {
        "status": status,
        "updated_at": utc_now(),
        "notes": notes,
    }
    if status == "completed" and PHASE_INDEX[phase] < len(PHASES) - 1:
        next_phase = PHASES[PHASE_INDEX[phase] + 1]
        if state["phases"][next_phase]["status"] == "pending":
            state["phases"][next_phase] = {
                "status": "in_progress",
                "updated_at": utc_now(),
                "notes": "",
            }
        state["current_phase"] = next_phase
    else:
        state["current_phase"] = phase
    save_state(pack, state)
    return state
