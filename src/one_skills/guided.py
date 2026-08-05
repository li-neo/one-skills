"""Recoverable, evidence-graded guided distillation sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import CONSENT_LEVELS, PERMISSIONS
from .models import Evidence
from .utils import append_jsonl, atomic_write, dump_json, iter_jsonl, new_id, utc_now

GUIDE_OBJECTS = (
    "person",
    "customer",
    "proposal",
    "skill",
    "methodology",
    "thought-system",
    "book",
    "document",
    "sop",
    "tool",
)
INTERACTION_MODES = ("conversation", "materials", "hybrid")
SESSION_STAGES = (
    "discover",
    "scope",
    "evidence_inventory",
    "interview",
    "map_confirm",
    "claim_review",
    "capability_confirm",
    "build",
    "evaluate",
    "ship",
    "evolve",
)
CHECKPOINTS = (
    "scope",
    "evidence_inventory",
    "map",
    "claims",
    "capabilities",
    "build",
    "evaluation",
    "ship",
)
CHECKPOINT_STATUSES = ("pending", "confirmed", "rejected")
EVENT_KINDS = (
    "answer",
    "source",
    "correction",
    "assumption",
    "evidence_gap",
    "observation",
    "result",
)
SESSION_EVIDENCE_CLASSES = (
    "self_report",
    "scenario_response",
    "observed_behavior",
    "documented_result",
    "third_party_view",
    "model_inference",
    "unknown",
)
PROFILE_BY_GUIDE_OBJECT = {
    "person": "person",
    "customer": "hybrid",
    "proposal": "content",
    "skill": "skill",
    "methodology": "methodology",
    "thought-system": "hybrid",
    "book": "content",
    "document": "content",
    "sop": "sop",
    "tool": "tool",
}
_STAGE_BY_CHECKPOINT = {
    "scope": "scope",
    "evidence_inventory": "evidence_inventory",
    "map": "map_confirm",
    "claims": "claim_review",
    "capabilities": "capability_confirm",
    "build": "build",
    "evaluation": "evaluate",
    "ship": "ship",
}
_CHECKPOINT_BY_STAGE = {
    stage: checkpoint for checkpoint, stage in _STAGE_BY_CHECKPOINT.items()
}
_EVIDENCE_QUALITY = {
    "self_report": (0.70, "low"),
    "scenario_response": (0.65, "medium"),
    "observed_behavior": (0.90, "none"),
    "documented_result": (0.95, "none"),
    "third_party_view": (0.75, "low"),
    "model_inference": (0.40, "high"),
    "unknown": (0.30, "high"),
}
_CLAIM_EVENT_KINDS = {"answer", "correction", "assumption", "observation", "result"}


class GuidedSessionError(RuntimeError):
    """Raised when a guided session violates a state or evidence gate."""


def _object_question(object_type: str) -> str:
    return {
        "person": "最近一次别人采用、拒绝或纠正你的建议是什么？你先注意到了什么？",
        "customer": "最近一次客户表达需求或异议时，哪些是原话，哪些只是团队推测？",
        "proposal": "最近一份被修改或否决的方案，真正阻断点和最终结果是什么？",
        "skill": "最近一次这个 Skill 成功、误触发或需要返工的真实任务是什么？",
        "methodology": "这个方法在哪两个场景有效，又在哪个场景失效？",
        "thought-system": "这套思想回答什么问题？最强反例或内部张力是什么？",
        "book": "书中哪个方法真正改变过一次判断或行动？结果如何？",
        "document": "这份文档最终要支持什么判断或行动，而不只是被总结？",
        "sop": "这个流程最常在哪个检查点、异常或交接处失败？",
        "tool": "用户要用这个工具完成什么任务？最危险的权限或失败是什么？",
    }[object_type]


def questions_for(state: dict[str, Any]) -> list[str]:
    stage = state["current_stage"]
    if stage == "discover":
        questions: list[str] = []
        if not state.get("target_capability"):
            questions.append("你最希望先复制哪一个高频、可验收的能力？")
        if not state.get("target_user") or not state.get("output_goal"):
            questions.append("谁会使用它，使用后要得到什么结果？")
        if not state.get("exclusions"):
            questions.append("它绝对不能替你或负责人做什么？")
        return (questions or ["请确认当前首期定位；准确后进入 scope。"])[:3]
    questions = {
        "scope": [
            "这个能力在什么场景触发，又在什么相似场景不应触发？",
            "什么结果算完成，哪些决定必须由人确认？",
        ],
        "evidence_inventory": [
            "能提供哪些文档、对话、修改记录、结果或反馈？没有也请明确记录。",
            "材料由谁所有，允许本地处理、进入私有 Pack 或发布到哪里？",
        ],
        "interview": [
            _object_question(state["object_type"]),
            "如果想不起成功或失败案例，最近一次相关任务是什么？",
        ],
        "map_confirm": ["对象地图中哪些准确、哪些仅适用于特定时期、哪些应删除？"],
        "claim_review": ["哪些 Claim 是事实或明确自述，哪些只是推断？有反例吗？"],
        "capability_confirm": ["候选能力能否处理新任务？何时必须停止或升级？"],
        "build": ["最终应生成一个原子 Skill，还是 Router 加多个原子 Skill？"],
        "evaluate": ["选择哪个低风险真实任务与无 Skill baseline 做盲比？"],
        "ship": ["谁可以安装使用？知识截止点、删除方法和回滚点是否确认？"],
        "evolve": ["本轮只优化知识、Recipe 或 Skill 中的哪一个维度？"],
    }
    return questions[stage][:3]


def _render_status(state: dict[str, Any]) -> str:
    lines = [
        "# Guided Distillation Session",
        "",
        f"- Session: `{state['session_id']}`",
        f"- Object: {state['subject']} (`{state['object_type']}`)",
        f"- Target capability: {state.get('target_capability') or 'pending'}",
        f"- Current stage: `{state['current_stage']}`",
        f"- Pack: `{state.get('pack_path') or 'not-created'}`",
        "",
        "## Evidence Counts",
        "",
    ]
    lines.extend(
        f"- `{name}`: {state['evidence_counts'].get(name, 0)}"
        for name in SESSION_EVIDENCE_CLASSES
    )
    lines.extend(["", "## Next Questions", ""])
    lines.extend(f"- {question}" for question in state["next_questions"])
    lines.extend(["", "## Checkpoints", ""])
    for name in CHECKPOINTS:
        checkpoint = state["checkpoints"][name]
        lines.append(
            f"- `{name}`: `{checkpoint['status']}`"
            + (f" - {checkpoint['notes']}" if checkpoint.get("notes") else "")
        )
    lines.extend(
        ["", "> SESSION_STATE.json and SESSION_EVENTS.jsonl are authoritative.", ""]
    )
    return "\n".join(lines)


def _render_intake(state: dict[str, Any]) -> str:
    return f"""# Guided Intake

- Object: {state["subject"]}
- Type: `{state["object_type"]}`
- Target capability: {state.get("target_capability") or "pending"}
- Target user: {state.get("target_user") or "pending"}
- Output goal: {state.get("output_goal") or "pending"}
- Access: `{state["access_level"]}`
- Consent: `{state["consent"]}`

## Confirmed Scope

<!-- Only user-confirmed statements belong here. -->

## Materials and Permissions

<!-- Record source, owner, permission, retention, and deletion method. -->

## Evidence Gaps

<!-- Record missing cases. Use scenario interviews; never invent historical evidence. -->
"""


def save_session(workspace: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    state["next_questions"] = questions_for(state)
    dump_json(workspace / "SESSION_STATE.json", state)
    atomic_write(workspace / "SESSION_STATUS.md", _render_status(state))


def validate_session_state(state: dict[str, Any]) -> list[str]:
    required = {
        "schema_version",
        "session_id",
        "subject",
        "object_type",
        "recommended_profile",
        "interaction_mode",
        "access_level",
        "consent",
        "current_stage",
        "stages",
        "checkpoints",
        "evidence_counts",
        "next_questions",
    }
    missing = required - set(state)
    if missing:
        return [f"missing fields: {', '.join(sorted(missing))}"]
    errors: list[str] = []
    if state.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if not isinstance(state.get("subject"), str) or not state["subject"].strip():
        errors.append("subject must not be empty")
    object_type = state.get("object_type")
    if object_type not in GUIDE_OBJECTS:
        errors.append("invalid object_type")
    elif state.get("recommended_profile") != PROFILE_BY_GUIDE_OBJECT[object_type]:
        errors.append("recommended_profile does not match object_type")
    if state.get("interaction_mode") not in INTERACTION_MODES:
        errors.append("invalid interaction_mode")
    if state.get("access_level") not in {"public", "authorized", "private-local"}:
        errors.append("invalid access_level")
    if state.get("consent") not in (*CONSENT_LEVELS, "not-applicable"):
        errors.append("invalid consent")
    if object_type == "person":
        if state.get("consent") in {"not-applicable", "prohibited"}:
            errors.append("person sessions require usable consent")
        if (
            state.get("consent") == "public-only"
            and state.get("access_level") != "public"
        ):
            errors.append("public-only consent requires public access")
    if state.get("current_stage") not in SESSION_STAGES:
        errors.append("invalid current_stage")
    if set(state.get("stages", {})) != set(SESSION_STAGES):
        errors.append("stages are incomplete")
    if set(state.get("checkpoints", {})) != set(CHECKPOINTS):
        errors.append("checkpoints are incomplete")
    elif any(
        item.get("status") not in CHECKPOINT_STATUSES
        for item in state["checkpoints"].values()
    ):
        errors.append("invalid checkpoint status")
    counts = state.get("evidence_counts", {})
    if set(counts) != set(SESSION_EVIDENCE_CLASSES) or any(
        not isinstance(value, int) or value < 0 for value in counts.values()
    ):
        errors.append("invalid evidence_counts")
    current = state.get("current_stage")
    if (
        current in SESSION_STAGES
        and state.get("stages", {}).get(current, {}).get("status") != "in_progress"
    ):
        errors.append("current stage must be in_progress")
    questions = state.get("next_questions", [])
    if len(questions) > 3 or any(
        not isinstance(item, str) or not item.strip() for item in questions
    ):
        errors.append("next_questions must contain at most three non-empty strings")
    return errors


def load_session(workspace: Path) -> dict[str, Any]:
    path = workspace / "SESSION_STATE.json"
    if not path.exists():
        raise GuidedSessionError(f"not a guided workspace: {path}")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GuidedSessionError(f"invalid session state: {exc}") from exc
    errors = validate_session_state(state)
    if errors:
        raise GuidedSessionError("invalid session state: " + "; ".join(errors))
    return state


def init_session(
    workspace: Path,
    subject: str,
    object_type: str,
    interaction_mode: str = "hybrid",
    target_capability: str | None = None,
    target_user: str | None = None,
    output_goal: str | None = None,
    access_level: str = "private-local",
    consent: str | None = None,
) -> dict[str, Any]:
    if object_type not in GUIDE_OBJECTS:
        raise GuidedSessionError(f"unsupported guided object: {object_type}")
    if interaction_mode not in INTERACTION_MODES:
        raise GuidedSessionError(f"unsupported interaction mode: {interaction_mode}")
    if access_level not in {"public", "authorized", "private-local"}:
        raise GuidedSessionError(f"unsupported access level: {access_level}")
    resolved_consent = consent or ("not-applicable" if object_type != "person" else "")
    if object_type == "person" and resolved_consent not in CONSENT_LEVELS:
        raise GuidedSessionError("person sessions require an explicit consent level")
    if resolved_consent == "prohibited":
        raise GuidedSessionError(
            "person distillation is prohibited by the consent contract"
        )
    if resolved_consent == "public-only" and access_level != "public":
        raise GuidedSessionError("public-only consent requires public access")
    if not subject.strip():
        raise GuidedSessionError("subject must not be empty")
    workspace = workspace.expanduser().resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise GuidedSessionError(f"guided workspace is not empty: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    state: dict[str, Any] = {
        "schema_version": "1.0",
        "session_id": new_id("session"),
        "created_at": now,
        "updated_at": now,
        "subject": subject.strip(),
        "object_type": object_type,
        "recommended_profile": PROFILE_BY_GUIDE_OBJECT[object_type],
        "interaction_mode": interaction_mode,
        "access_level": access_level,
        "consent": resolved_consent,
        "target_capability": (target_capability or "").strip(),
        "target_user": (target_user or "").strip(),
        "output_goal": (output_goal or "").strip(),
        "exclusions": [],
        "current_stage": "discover",
        "stages": {
            stage: {
                "status": "in_progress" if stage == "discover" else "pending",
                "updated_at": now if stage == "discover" else None,
                "notes": "",
            }
            for stage in SESSION_STAGES
        },
        "checkpoints": {
            name: {"status": "pending", "updated_at": None, "notes": ""}
            for name in CHECKPOINTS
        },
        "evidence_counts": {name: 0 for name in SESSION_EVIDENCE_CLASSES},
        "source_inventory": [],
        "assumptions": [],
        "evidence_gaps": [],
        "corrections": [],
        "next_questions": [],
        "pack_path": None,
        "exported_source": None,
    }
    atomic_write(workspace / "SESSION_EVENTS.jsonl", "")
    atomic_write(workspace / "INTAKE.md", _render_intake(state))
    save_session(workspace, state)
    return state


def update_session_profile(
    workspace: Path,
    target_capability: str | None = None,
    target_user: str | None = None,
    output_goal: str | None = None,
    exclusions: list[str] | None = None,
) -> dict[str, Any]:
    state = load_session(workspace)
    for key, value in (
        ("target_capability", target_capability),
        ("target_user", target_user),
        ("output_goal", output_goal),
    ):
        if value is not None:
            state[key] = value.strip()
    for exclusion in exclusions or []:
        value = exclusion.strip()
        if value and value not in state["exclusions"]:
            state["exclusions"].append(value)
    save_session(workspace, state)
    atomic_write(workspace / "INTAKE.md", _render_intake(state))
    return state


def load_events(workspace: Path) -> list[dict[str, Any]]:
    try:
        return list(iter_jsonl(workspace / "SESSION_EVENTS.jsonl"))
    except json.JSONDecodeError as exc:
        raise GuidedSessionError(f"invalid session event ledger: {exc}") from exc


def record_event(workspace: Path, event: dict[str, Any]) -> dict[str, Any]:
    state = load_session(workspace)
    kind = str(event.get("kind", "")).strip()
    content = str(event.get("content", "")).strip()
    evidence_class = str(event.get("evidence_class", "unknown")).strip()
    permission = str(event.get("permission", "unknown")).strip()
    locator = str(event.get("locator", "")).strip()
    if kind not in EVENT_KINDS:
        raise GuidedSessionError(f"unknown event kind: {kind}")
    if not content:
        raise GuidedSessionError("event content must not be empty")
    if evidence_class not in SESSION_EVIDENCE_CLASSES:
        raise GuidedSessionError(f"unknown evidence class: {evidence_class}")
    if permission not in PERMISSIONS:
        raise GuidedSessionError(f"unknown permission: {permission}")
    strong = {"observed_behavior", "documented_result", "third_party_view"}
    if kind == "answer" and evidence_class in strong:
        raise GuidedSessionError(
            "an answer cannot be promoted to observed, documented, or third-party evidence"
        )
    if evidence_class in strong and (not locator or permission == "unknown"):
        raise GuidedSessionError(
            f"{evidence_class} requires a locator and explicit permission"
        )
    normalized = {
        "id": new_id("session-event"),
        "kind": kind,
        "content": content,
        "evidence_class": evidence_class,
        "permission": permission,
        "locator": locator,
        "stage": state["current_stage"],
        "recorded_at": utc_now(),
        "notes": str(event.get("notes", "")).strip(),
    }
    append_jsonl(workspace / "SESSION_EVENTS.jsonl", normalized)
    state["evidence_counts"][evidence_class] += 1
    collection = {
        "source": "source_inventory",
        "assumption": "assumptions",
        "evidence_gap": "evidence_gaps",
        "correction": "corrections",
    }.get(kind)
    if collection:
        state[collection].append(
            {
                "event_id": normalized["id"],
                "content": content,
                "locator": locator,
                "permission": permission,
            }
        )
    save_session(workspace, state)
    return normalized


def confirm_checkpoint(
    workspace: Path, checkpoint: str, status: str, notes: str = ""
) -> dict[str, Any]:
    state = load_session(workspace)
    if checkpoint not in CHECKPOINTS:
        raise GuidedSessionError(f"unknown checkpoint: {checkpoint}")
    if status not in CHECKPOINT_STATUSES:
        raise GuidedSessionError(f"unknown checkpoint status: {status}")
    if status == "confirmed" and SESSION_STAGES.index(
        state["current_stage"]
    ) < SESSION_STAGES.index(_STAGE_BY_CHECKPOINT[checkpoint]):
        raise GuidedSessionError(f"cannot confirm a future checkpoint: {checkpoint}")
    state["checkpoints"][checkpoint] = {
        "status": status,
        "updated_at": utc_now(),
        "notes": notes.strip(),
    }
    save_session(workspace, state)
    return state["checkpoints"][checkpoint]


def advance_session(workspace: Path) -> dict[str, Any]:
    state = load_session(workspace)
    current = state["current_stage"]
    index = SESSION_STAGES.index(current)
    if index == len(SESSION_STAGES) - 1:
        raise GuidedSessionError("session is already at evolve")
    if current == "discover" and not state.get("target_capability"):
        raise GuidedSessionError("set a target capability before entering scope")
    if current == "interview" and not load_events(workspace):
        raise GuidedSessionError(
            "record evidence or an explicit evidence gap before map confirmation"
        )
    checkpoint = _CHECKPOINT_BY_STAGE.get(current)
    if checkpoint and state["checkpoints"][checkpoint]["status"] != "confirmed":
        raise GuidedSessionError(f"confirm checkpoint before advancing: {checkpoint}")
    now = utc_now()
    state["stages"][current] = {
        "status": "completed",
        "updated_at": now,
        "notes": "passed guided stage gate",
    }
    next_stage = SESSION_STAGES[index + 1]
    state["stages"][next_stage] = {
        "status": "in_progress",
        "updated_at": now,
        "notes": "",
    }
    state["current_stage"] = next_stage
    save_session(workspace, state)
    return state


def export_session_source(workspace: Path, output: Path | None = None) -> Path:
    state = load_session(workspace)
    events = load_events(workspace)
    if not events:
        raise GuidedSessionError("session has no events to export")
    target = (
        (output or workspace / "sources" / "guided-session.md").expanduser().resolve()
    )
    lines = [
        "# Guided Distillation Conversation Source",
        "",
        f"- Session: `{state['session_id']}`",
        f"- Subject: {state['subject']}",
        f"- Object type: `{state['object_type']}`",
        f"- Target capability: {state.get('target_capability') or 'unconfirmed'}",
        f"- Exported at: {utc_now()}",
        "",
        "> self_report, scenario_response, and model_inference are not observed behavior or verified results.",
        "",
    ]
    for event in events:
        lines.extend(
            [
                f"## {event['id']}",
                "",
                f"- kind: `{event['kind']}`",
                f"- evidence_class: `{event['evidence_class']}`",
                f"- permission: `{event['permission']}`",
                f"- original_locator: `{event.get('locator') or 'conversation'}`",
                f"- stage: `{event['stage']}`",
                "",
                event["content"],
                "",
            ]
        )
    atomic_write(target, "\n".join(lines).rstrip() + "\n")
    state["exported_source"] = str(target)
    save_session(workspace, state)
    return target


def _materialize_session_evidence(pack: Path, events: list[dict[str, Any]]) -> int:
    from .database import KnowledgeDB
    from .pipeline import workspace_for
    from .utils import append_jsonl, load_json

    manifest = load_json(pack / "SOURCE_MANIFEST.json")
    guided_source = manifest["sources"][0]
    document_id = guided_source["document_id"]
    source_path = guided_source["source"]
    materialized = 0
    root = workspace_for(pack)
    with KnowledgeDB(root / ".one" / "knowledge.db") as database:
        chunks = {
            row["section_path"]: row
            for row in database.rows(
                "SELECT id, section_path, source_locator FROM chunks "
                "WHERE document_id = ? AND document_version = ?",
                (document_id, guided_source["document_version"]),
            )
        }
        for event in events:
            if event["kind"] not in _CLAIM_EVENT_KINDS:
                continue
            chunk = chunks.get(event["id"])
            confidence, inference_level = _EVIDENCE_QUALITY[event["evidence_class"]]
            locator = (
                chunk["source_locator"]
                if chunk
                else event.get("locator") or f"{source_path}#{event['id']}"
            )
            evidence = Evidence(
                id=event["id"],
                claim=event["content"],
                evidence_type=event["evidence_class"],
                source=document_id,
                locator=locator,
                confidence=confidence,
                inference_level=inference_level,
                permission=event["permission"],
                notes=f"guided session {event['stage']} / {event['kind']}",
                recorded_at=event["recorded_at"],
            )
            append_jsonl(pack / "EVIDENCE_LEDGER.jsonl", evidence.to_dict())
            database.add_claim(
                evidence.claim,
                evidence.confidence,
                [chunk["id"]] if chunk else [],
                status="needs_evidence" if inference_level == "high" else "active",
                claim_id=evidence.id,
            )
            materialized += 1
    return materialized


def create_pack_from_session(
    workspace: Path,
    output_root: Path,
    mode: str = "standard",
    extra_sources: list[str] | None = None,
) -> tuple[Path, int]:
    state = load_session(workspace)
    if not state.get("target_capability"):
        raise GuidedSessionError("set a target capability before creating a Pack")
    for checkpoint in ("scope", "evidence_inventory"):
        if state["checkpoints"][checkpoint]["status"] != "confirmed":
            raise GuidedSessionError(
                f"confirm checkpoint before creating a Pack: {checkpoint}"
            )
    source = export_session_source(workspace)
    from .pipeline import create_pack

    pack = create_pack(
        output_root,
        [str(source), *(extra_sources or [])],
        state["recommended_profile"],
        mode,
        state["target_capability"],
        state["access_level"],
        state["consent"] if state["object_type"] == "person" else None,
    )
    count = _materialize_session_evidence(pack, load_events(workspace))
    state = load_session(workspace)
    state["pack_path"] = str(pack)
    save_session(workspace, state)
    return pack, count


def validate_guided_workspace(workspace: Path) -> list[Any]:
    from .validation import Finding

    findings: list[Finding] = []
    try:
        state = json.loads(
            (workspace / "SESSION_STATE.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        return [
            Finding(
                "error",
                "session.parse",
                str(exc),
                str(workspace / "SESSION_STATE.json"),
            )
        ]
    for message in validate_session_state(state):
        findings.append(
            Finding(
                "error", "session.state", message, str(workspace / "SESSION_STATE.json")
            )
        )
    try:
        events = load_events(workspace)
    except GuidedSessionError as exc:
        findings.append(
            Finding(
                "error",
                "session.events",
                str(exc),
                str(workspace / "SESSION_EVENTS.jsonl"),
            )
        )
        return findings
    ids: set[str] = set()
    actual_counts = {name: 0 for name in SESSION_EVIDENCE_CLASSES}
    required = {
        "id",
        "kind",
        "content",
        "evidence_class",
        "permission",
        "locator",
        "stage",
        "recorded_at",
    }
    for number, event in enumerate(events, start=1):
        location = f"{workspace / 'SESSION_EVENTS.jsonl'}:{number}"
        if not required <= set(event):
            findings.append(
                Finding("error", "session.event", "missing required fields", location)
            )
            continue
        if event["id"] in ids:
            findings.append(
                Finding("error", "session.event_id", "duplicate event id", location)
            )
        ids.add(event["id"])
        if event["kind"] not in EVENT_KINDS:
            findings.append(
                Finding("error", "session.event_kind", "invalid event kind", location)
            )
        evidence_class = event["evidence_class"]
        if evidence_class not in SESSION_EVIDENCE_CLASSES:
            findings.append(
                Finding(
                    "error",
                    "session.evidence_class",
                    "invalid evidence class",
                    location,
                )
            )
            continue
        if (
            event["permission"] not in PERMISSIONS
            or event["stage"] not in SESSION_STAGES
        ):
            findings.append(
                Finding(
                    "error",
                    "session.event_scope",
                    "invalid permission or stage",
                    location,
                )
            )
        if event["kind"] == "answer" and evidence_class in {
            "observed_behavior",
            "documented_result",
            "third_party_view",
        }:
            findings.append(
                Finding(
                    "error",
                    "session.evidence_promotion",
                    "an answer cannot be promoted to strong external evidence",
                    location,
                )
            )
        actual_counts[evidence_class] += 1
    if actual_counts != state.get("evidence_counts"):
        findings.append(
            Finding(
                "error",
                "session.counts",
                "evidence_counts do not match the event ledger",
                str(workspace / "SESSION_STATE.json"),
            )
        )
    for filename in ("SESSION_EVENTS.jsonl", "SESSION_STATUS.md", "INTAKE.md"):
        if not (workspace / filename).exists():
            findings.append(
                Finding(
                    "error",
                    "session.file",
                    f"missing {filename}",
                    str(workspace / filename),
                )
            )
    return findings
