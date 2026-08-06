"""Command-line interface for the complete one-skills workflow."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .api import create_api_server
from .batch import distill_batch, load_jobs
from .benchmark import run_profile_benchmark
from .compiler import export_profile_templates
from .constants import CONSENT_LEVELS, MODES, PHASES
from .database import KnowledgeDB
from .delivery import (
    DeliveryError,
    export_pack,
    install_pack,
    prepare_darwin,
    release_pack,
)
from .evaluation import evaluate_pack
from .experience import (
    ExperienceError,
    load_experiences,
    mine_experience_candidates,
    record_experience,
)
from .guided import (
    CHECKPOINT_STATUSES,
    CHECKPOINTS,
    EVENT_KINDS,
    GUIDE_OBJECTS,
    INTERACTION_MODES,
    SESSION_EVIDENCE_CLASSES,
    GuidedSessionError,
    advance_session,
    confirm_checkpoint,
    create_pack_from_session,
    export_session_source,
    init_session,
    load_session,
    record_event,
    update_session_profile,
    validate_guided_workspace,
)
from .ingest import IngestionError
from .jobs import JobQueue, run_worker_once
from .learning import (
    LearningError,
    build_learning_path,
    init_learner,
    load_learner,
    next_learning_node,
    record_attempt,
)
from .pipeline import (
    PipelineError,
    advance_phase,
    approve_and_compile,
    create_pack,
    init_workspace,
    lineage,
    load_state,
    revoke_source,
    select_regression_tests,
    update_pack,
    verify_and_compile_with_model,
    workspace_for,
)
from .postgres import PostgresBackend
from .provider import OpenAICompatibleProvider, ProviderConfig, ProviderError
from .recipes import Recipe, promote_recipe, promotion_decision
from .retrieval import HybridRetriever, local_embedding
from .routing import route_intent
from .skill_retrieval import search_skills
from .source_quality import (
    SourceQualityError,
    audit_source_catalog,
    write_source_catalog_template,
)
from .validation import summary, validate_pack, validate_skill


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_init(args: argparse.Namespace) -> int:
    root = init_workspace(_path(args.path), args.mode)
    print(f"initialized one-skills workspace: {root}")
    return 0


def cmd_distill(args: argparse.Namespace) -> int:
    pack = create_pack(
        _path(args.workspace),
        args.source or [],
        args.type,
        args.mode,
        args.name,
        args.access,
        args.consent,
        _path(args.source_catalog) if args.source_catalog else None,
    )
    state = load_state(pack)
    _print(
        {
            "pack": str(pack),
            "phase": state["current_phase"],
            "status": state["phases"][state["current_phase"]]["status"],
            "next": "review verified/decisions.json, then run `one approve` with an independently verified candidate",
        }
    )
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    pack = _path(args.pack)
    state = load_state(pack)
    metadata = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    _print(
        {
            "pack": metadata,
            "current_phase": state["current_phase"],
            "phases": {phase: state["phases"][phase]["status"] for phase in PHASES},
            "skills": [path.parent.name for path in (pack / "skills").glob("*/SKILL.md")],
        }
    )
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    _print(update_pack(_path(args.pack), args.source))
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    state = advance_phase(_path(args.pack), args.phase, args.status, args.notes or "")
    _print({"current_phase": state["current_phase"], "phases": state["phases"]})
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    skill = approve_and_compile(_path(args.pack), args.candidate, args.reason)
    print(f"compiled Skill: {skill}")
    return 0


def cmd_verify_model(args: argparse.Namespace) -> int:
    config = ProviderConfig.from_environment()
    if config is None:
        raise ProviderError(
            "set ONE_SKILLS_MODEL_BASE_URL, ONE_SKILLS_MODEL_API_KEY, and ONE_SKILLS_MODEL"
        )
    skills = verify_and_compile_with_model(
        _path(args.pack),
        OpenAICompatibleProvider(config),
        args.allow_sensitive_data,
        not args.skip_semantic_extract,
    )
    _print({"compiled": [str(skill) for skill in skills], "count": len(skills)})
    return 0 if skills else 1


def cmd_search(args: argparse.Namespace) -> int:
    workspace = workspace_for(_path(args.workspace))
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        results = HybridRetriever(database, args.tenant, args.principal).search(
            args.query, set(args.access), args.limit
        )
    _print(
        [
            {
                "id": item["id"],
                "score": item["score"],
                "section": item["section_path"],
                "locator": item["source_locator"],
                "text": item["text"][:500],
            }
            for item in results
        ]
    )
    return 0


def cmd_skill_search(args: argparse.Namespace) -> int:
    result = search_skills(
        args.query,
        [_path(root) for root in args.root],
        args.limit,
        args.minimum_score,
        args.minimum_margin,
    )
    _print(result)
    return 1 if result["status"] == "abstain" else 0


def cmd_route(args: argparse.Namespace) -> int:
    _print(route_intent(args.intent, args.source))
    return 0


def cmd_source(args: argparse.Namespace) -> int:
    if args.source_command == "template":
        path = write_source_catalog_template(_path(args.output))
        _print({"catalog_template": str(path)})
        return 0
    report = audit_source_catalog(_path(args.catalog), args.type, args.mode)
    if args.output:
        from .utils import dump_json

        dump_json(_path(args.output), report)
    _print(report)
    return 0 if report["status"] == "passed" else 1


def cmd_learn(args: argparse.Namespace) -> int:
    pack = _path(args.pack)
    if args.learn_command == "path":
        _print(build_learning_path(pack))
    elif args.learn_command == "init":
        _print(init_learner(pack, args.learner))
    elif args.learn_command == "record":
        _print(
            record_attempt(
                pack,
                args.learner,
                args.node,
                args.score,
                args.evidence,
            )
        )
    elif args.learn_command == "next":
        _print(next_learning_node(pack, args.learner) or {"status": "complete"})
    else:
        _print(load_learner(pack, args.learner))
    return 0


def cmd_experience(args: argparse.Namespace) -> int:
    pack = _path(args.pack)
    if args.experience_command == "record":
        _print(
            record_experience(
                pack,
                args.skill,
                args.task_signature,
                args.outcome,
                args.result_summary,
                args.evidence_locator,
                args.correction or "",
                args.access,
                args.scope,
            )
        )
    elif args.experience_command == "mine":
        _print(mine_experience_candidates(pack, args.minimum_occurrences))
    else:
        events = load_experiences(pack)
        _print({"count": len(events), "events": events})
    return 0


def cmd_acl(args: argparse.Namespace) -> int:
    workspace = workspace_for(_path(args.workspace))
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        if args.acl_command == "tenant":
            database.create_tenant(args.tenant, args.name)
        elif args.acl_command == "principal":
            database.create_principal(args.tenant, args.principal, args.name)
        else:
            database.grant_acl(
                args.tenant,
                args.principal,
                args.asset_type,
                args.asset_id,
                args.permission,
            )
    _print({"status": "ok", "operation": args.acl_command})
    return 0


def cmd_job(args: argparse.Namespace) -> int:
    workspace = workspace_for(_path(args.workspace))
    if args.job_command == "worker":
        result = run_worker_once(workspace, args.owner)
        _print(result or {"status": "idle"})
        return 0
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        queue = JobQueue(database)
        if args.job_command == "submit":
            payload = json.loads(_path(args.payload).read_text(encoding="utf-8"))
            job_id = queue.enqueue(args.type, payload, args.max_attempts)
            _print({"job_id": job_id, "status": "queued"})
        else:
            _print(queue.get(args.id))
    return 0


def cmd_lineage(args: argparse.Namespace) -> int:
    _print(lineage(_path(args.workspace), args.type, args.id))
    return 0


def cmd_revoke_source(args: argparse.Namespace) -> int:
    _print(revoke_source(_path(args.workspace), args.id, args.reason))
    return 0


def cmd_regression_plan(args: argparse.Namespace) -> int:
    _print(select_regression_tests(_path(args.pack), args.skill))
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    workspace = workspace_for(_path(args.workspace))
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        if args.memory_command == "subject":
            subject_id = database.add_person_subject(args.name, args.relation, args.access)
            _print({"subject_id": subject_id})
        else:
            fact_id = database.mutate_person_fact(
                args.action,
                args.subject,
                args.dimension,
                args.statement,
                args.confidence,
                args.access,
                args.supersedes,
                local_embedding(args.statement),
            )
            _print({"fact_id": fact_id, "action": args.action})
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    target = _path(args.target)
    if (target / "SESSION_STATE.json").exists():
        findings = validate_guided_workspace(target)
    elif (target / "PIPELINE_STATE.json").exists():
        findings = validate_pack(target)
    else:
        findings = validate_skill(target)
    result = summary(findings)
    _print(result)
    return 1 if result["errors"] else 0


def cmd_test(args: argparse.Namespace) -> int:
    report = evaluate_pack(_path(args.pack), _path(args.results) if args.results else None)
    _print(report)
    return 1 if report["errors"] or not report["skills"] else 0


def cmd_install(args: argparse.Namespace) -> int:
    actions = install_pack(
        _path(args.pack),
        _path(args.target) if args.target else None,
        args.dry_run,
        args.force,
    )
    _print(actions)
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    _print(release_pack(_path(args.pack)))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    archive = export_pack(_path(args.pack), _path(args.output), args.runtime)
    print(f"exported and verified: {archive}")
    return 0


def cmd_evolve(args: argparse.Namespace) -> int:
    request = prepare_darwin(
        _path(args.pack),
        args.skill,
        _path(args.comparisons) if args.comparisons else None,
    )
    _print(request)
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    suite = _path(args.suite)
    report = run_profile_benchmark(suite, _path(args.output) if args.output else None)
    _print(report)
    return 0 if report["rate"] == 1.0 else 1


def cmd_batch(args: argparse.Namespace) -> int:
    report = distill_batch(_path(args.workspace), load_jobs(_path(args.manifest)), args.workers)
    _print(report)
    return 1 if report["failed"] else 0


def cmd_profiles(args: argparse.Namespace) -> int:
    path = export_profile_templates(_path(args.output))
    print(f"exported Profile templates: {path}")
    return 0


def cmd_guide(args: argparse.Namespace) -> int:
    workspace = _path(args.workspace)
    if args.guide_command == "init":
        state = init_session(
            workspace,
            args.subject,
            args.object_type,
            args.interaction_mode,
            args.target_capability,
            args.target_user,
            args.output_goal,
            args.access,
            args.consent,
        )
        _print(
            {
                "workspace": str(workspace),
                "session_id": state["session_id"],
                "current_stage": state["current_stage"],
                "next_questions": state["next_questions"],
            }
        )
    elif args.guide_command == "set":
        state = update_session_profile(
            workspace,
            args.target_capability,
            args.target_user,
            args.output_goal,
            args.exclude,
        )
        _print(
            {
                "current_stage": state["current_stage"],
                "target_capability": state["target_capability"],
                "target_user": state["target_user"],
                "output_goal": state["output_goal"],
                "exclusions": state["exclusions"],
                "next_questions": state["next_questions"],
            }
        )
    elif args.guide_command == "status":
        state = load_session(workspace)
        _print(
            {
                key: state[key]
                for key in (
                    "session_id",
                    "subject",
                    "object_type",
                    "recommended_profile",
                    "target_capability",
                    "current_stage",
                    "evidence_counts",
                    "evidence_gaps",
                    "checkpoints",
                    "next_questions",
                    "pack_path",
                )
            }
        )
    elif args.guide_command == "record":
        event = (
            json.loads(_path(args.from_file).read_text(encoding="utf-8"))
            if args.from_file
            else {
                "kind": args.kind,
                "content": args.content,
                "evidence_class": args.evidence_class,
                "permission": args.permission,
                "locator": args.locator or "",
                "notes": args.notes or "",
            }
        )
        _print(record_event(workspace, event))
    elif args.guide_command == "confirm":
        result = confirm_checkpoint(
            workspace, args.checkpoint, args.status, args.notes or ""
        )
        _print({"checkpoint": args.checkpoint, **result})
    elif args.guide_command == "advance":
        state = advance_session(workspace)
        _print(
            {
                "current_stage": state["current_stage"],
                "next_questions": state["next_questions"],
            }
        )
    elif args.guide_command == "export":
        target = export_session_source(
            workspace, _path(args.output) if args.output else None
        )
        _print({"source": str(target)})
    else:
        pack, evidence_count = create_pack_from_session(
            workspace, _path(args.output), args.mode, args.source
        )
        _print(
            {
                "pack": str(pack),
                "guided_evidence_materialized": evidence_count,
                "current_phase": load_state(pack)["current_phase"],
            }
        )
    return 0


def cmd_postgres(args: argparse.Namespace) -> int:
    dsn = os.getenv("ONE_SKILLS_POSTGRES_DSN")
    if not dsn:
        raise ValueError("set ONE_SKILLS_POSTGRES_DSN")
    with PostgresBackend(dsn) as backend:
        if args.postgres_command == "init":
            backend.initialize(_path(args.migration))
            result = backend.health()
        elif args.postgres_command == "health":
            result = backend.health()
        elif args.postgres_command == "migrate":
            result = {
                "migrated": backend.migrate_from_sqlite(_path(args.sqlite), args.batch_size)
            }
        else:
            result = backend.load_test(args.query, args.iterations, args.tenant, args.principal)
    _print(result)
    return 0


def cmd_recipe(args: argparse.Namespace) -> int:
    workspace = workspace_for(_path(args.workspace))
    registry_path = workspace / ".one" / "recipes.json"
    if args.recipe_command == "list":
        _print(json.loads(registry_path.read_text(encoding="utf-8")))
        return 0
    if args.recipe_command == "evaluate":
        baseline = json.loads(_path(args.baseline).read_text(encoding="utf-8"))
        candidate = json.loads(_path(args.candidate).read_text(encoding="utf-8"))
        budgets = json.loads(_path(args.budgets).read_text(encoding="utf-8"))
        decision = promotion_decision(baseline, candidate, budgets)
        if args.output:
            from .utils import dump_json

            dump_json(_path(args.output), decision)
        _print(decision)
        return 0 if decision["promote"] else 1
    recipe = Recipe(**json.loads(_path(args.recipe).read_text(encoding="utf-8")))
    decision = json.loads(_path(args.decision).read_text(encoding="utf-8"))
    promote_recipe(registry_path, recipe, decision)
    _print({"status": "promoted", "profile": recipe.profile, "version": recipe.version})
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    workspace = workspace_for(_path(args.workspace))
    server = create_api_server(
        workspace,
        args.host,
        args.port,
        os.getenv("ONE_SKILLS_API_TOKEN"),
    )
    print(f"one-skills API listening on http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="one", description="Evidence-first Skill distillation and knowledge system")
    parser.add_argument("--version", action="version", version=f"one-skills {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="initialize a workspace and SQLite knowledge base")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--mode", choices=MODES, default="standard")
    init.set_defaults(func=cmd_init)

    distill = commands.add_parser("distill", help="ingest, index, map, extract, and verify sources")
    distill.add_argument("--source", action="append")
    distill.add_argument(
        "--source-catalog",
        help="quality-gated source catalog whose selected ingest paths are added",
    )
    distill.add_argument("--workspace", default=".")
    distill.add_argument("--type", default="auto", help="built-in or entry-point Profile name")
    distill.add_argument("--mode", choices=MODES, default="standard")
    distill.add_argument("--name")
    distill.add_argument("--access", choices=("public", "authorized", "private-local"), default="private-local")
    distill.add_argument("--consent", choices=CONSENT_LEVELS)
    distill.set_defaults(func=cmd_distill)

    inspect = commands.add_parser("inspect", help="inspect Pack state")
    inspect.add_argument("pack")
    inspect.set_defaults(func=cmd_inspect)

    update = commands.add_parser("update", help="incrementally ingest changed sources")
    update.add_argument("pack")
    update.add_argument("--source", action="append", required=True)
    update.set_defaults(func=cmd_update)

    advance = commands.add_parser("advance", help="advance or block a phase without skipping")
    advance.add_argument("pack")
    advance.add_argument("--phase", choices=PHASES, required=True)
    advance.add_argument("--status", choices=("pending", "in_progress", "completed", "blocked"), required=True)
    advance.add_argument("--notes")
    advance.set_defaults(func=cmd_advance)

    approve = commands.add_parser("approve", help="record independent V2 approval and compile a Skill")
    approve.add_argument("pack")
    approve.add_argument("--candidate", required=True)
    approve.add_argument("--reason", required=True)
    approve.set_defaults(func=cmd_approve)

    verify_model = commands.add_parser(
        "verify-model",
        help="run independent V1-V3 verification and capability modeling",
    )
    verify_model.add_argument("pack")
    verify_model.add_argument(
        "--allow-sensitive-data",
        action="store_true",
        help="explicitly authorize sending authorized/private-local evidence to the model endpoint",
    )
    verify_model.add_argument(
        "--skip-semantic-extract",
        action="store_true",
        help="verify existing candidates without running parallel semantic extractors",
    )
    verify_model.set_defaults(func=cmd_verify_model)

    search = commands.add_parser("search", help="ACL-aware keyword, semantic, and graph retrieval")
    search.add_argument("query")
    search.add_argument("--workspace", default=".")
    search.add_argument("--access", action="append", default=["public"])
    search.add_argument("--tenant", default="local")
    search.add_argument("--principal", default="local-user")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)

    skill_search = commands.add_parser(
        "skill-search",
        help="field-aware retrieval over Agent Skill directories",
    )
    skill_search.add_argument("query")
    skill_search.add_argument("--root", action="append", required=True)
    skill_search.add_argument("--limit", type=int, default=10)
    skill_search.add_argument("--minimum-score", type=float, default=0.10)
    skill_search.add_argument("--minimum-margin", type=float, default=0.025)
    skill_search.set_defaults(func=cmd_skill_search)

    route = commands.add_parser(
        "route",
        help="explainably route an intent to a distillation object or abstain",
    )
    route.add_argument("--intent", required=True)
    route.add_argument("--source", action="append", default=[])
    route.set_defaults(func=cmd_route)

    source = commands.add_parser(
        "source",
        help="create or audit high-quality source catalogs",
    )
    source_commands = source.add_subparsers(dest="source_command", required=True)
    source_template = source_commands.add_parser("template")
    source_template.add_argument("--output", required=True)
    source_template.set_defaults(func=cmd_source)
    source_audit = source_commands.add_parser("audit")
    source_audit.add_argument("--catalog", required=True)
    source_audit.add_argument("--type", default="content")
    source_audit.add_argument("--mode", choices=MODES, default="standard")
    source_audit.add_argument("--output")
    source_audit.set_defaults(func=cmd_source)

    learn = commands.add_parser(
        "learn",
        help="build a prerequisite path and track learner mastery",
    )
    learn_commands = learn.add_subparsers(dest="learn_command", required=True)
    learn_path = learn_commands.add_parser("path")
    learn_path.add_argument("pack")
    learn_path.set_defaults(func=cmd_learn)
    learn_init = learn_commands.add_parser("init")
    learn_init.add_argument("pack")
    learn_init.add_argument("--learner", required=True)
    learn_init.set_defaults(func=cmd_learn)
    learn_record = learn_commands.add_parser("record")
    learn_record.add_argument("pack")
    learn_record.add_argument("--learner", required=True)
    learn_record.add_argument("--node", required=True)
    learn_record.add_argument("--score", type=float, required=True)
    learn_record.add_argument("--evidence", required=True)
    learn_record.set_defaults(func=cmd_learn)
    learn_next = learn_commands.add_parser("next")
    learn_next.add_argument("pack")
    learn_next.add_argument("--learner", required=True)
    learn_next.set_defaults(func=cmd_learn)
    learn_status = learn_commands.add_parser("status")
    learn_status.add_argument("pack")
    learn_status.add_argument("--learner", required=True)
    learn_status.set_defaults(func=cmd_learn)

    experience = commands.add_parser(
        "experience",
        help="record deployment feedback and mine conservative evolution candidates",
    )
    experience_commands = experience.add_subparsers(
        dest="experience_command",
        required=True,
    )
    experience_record = experience_commands.add_parser("record")
    experience_record.add_argument("pack")
    experience_record.add_argument("--skill", required=True)
    experience_record.add_argument("--task-signature", required=True)
    experience_record.add_argument(
        "--outcome",
        choices=("success", "failure", "corrected"),
        required=True,
    )
    experience_record.add_argument("--result-summary", required=True)
    experience_record.add_argument("--evidence-locator", required=True)
    experience_record.add_argument("--correction")
    experience_record.add_argument(
        "--access",
        choices=("public", "authorized", "private-local", "unknown"),
        default="private-local",
    )
    experience_record.add_argument(
        "--scope",
        choices=("training", "evaluation"),
        default="training",
    )
    experience_record.set_defaults(func=cmd_experience)
    experience_mine = experience_commands.add_parser("mine")
    experience_mine.add_argument("pack")
    experience_mine.add_argument("--minimum-occurrences", type=int, default=2)
    experience_mine.set_defaults(func=cmd_experience)
    experience_status = experience_commands.add_parser("status")
    experience_status.add_argument("pack")
    experience_status.set_defaults(func=cmd_experience)

    acl = commands.add_parser("acl", help="manage tenant, principal, and asset grants")
    acl_commands = acl.add_subparsers(dest="acl_command", required=True)
    acl_tenant = acl_commands.add_parser("tenant")
    acl_tenant.add_argument("--workspace", default=".")
    acl_tenant.add_argument("--tenant", required=True)
    acl_tenant.add_argument("--name", required=True)
    acl_tenant.set_defaults(func=cmd_acl)
    acl_principal = acl_commands.add_parser("principal")
    acl_principal.add_argument("--workspace", default=".")
    acl_principal.add_argument("--tenant", required=True)
    acl_principal.add_argument("--principal", required=True)
    acl_principal.add_argument("--name", required=True)
    acl_principal.set_defaults(func=cmd_acl)
    acl_grant = acl_commands.add_parser("grant")
    acl_grant.add_argument("--workspace", default=".")
    acl_grant.add_argument("--tenant", required=True)
    acl_grant.add_argument("--principal", required=True)
    acl_grant.add_argument("--asset-type", required=True)
    acl_grant.add_argument("--asset-id", required=True)
    acl_grant.add_argument("--permission", choices=("read", "write", "owner"), required=True)
    acl_grant.set_defaults(func=cmd_acl)

    job = commands.add_parser("job", help="submit, inspect, or execute persistent jobs")
    job_commands = job.add_subparsers(dest="job_command", required=True)
    job_submit = job_commands.add_parser("submit")
    job_submit.add_argument("--workspace", default=".")
    job_submit.add_argument("--type", choices=("distill", "update", "benchmark"), required=True)
    job_submit.add_argument("--payload", required=True, help="JSON payload file")
    job_submit.add_argument("--max-attempts", type=int, default=3)
    job_submit.set_defaults(func=cmd_job)
    job_status = job_commands.add_parser("status")
    job_status.add_argument("--workspace", default=".")
    job_status.add_argument("--id", required=True)
    job_status.set_defaults(func=cmd_job)
    job_worker = job_commands.add_parser("worker")
    job_worker.add_argument("--workspace", default=".")
    job_worker.add_argument("--owner", required=True)
    job_worker.set_defaults(func=cmd_job)

    lineage_parser = commands.add_parser("lineage", help="list transitive descendants of an asset")
    lineage_parser.add_argument("--workspace", default=".")
    lineage_parser.add_argument("--type", required=True)
    lineage_parser.add_argument("--id", required=True)
    lineage_parser.set_defaults(func=cmd_lineage)

    revoke = commands.add_parser("source-revoke", help="revoke a source and invalidate dependent Packs")
    revoke.add_argument("--workspace", default=".")
    revoke.add_argument("--id", required=True)
    revoke.add_argument("--reason", required=True)
    revoke.set_defaults(func=cmd_revoke_source)

    regression = commands.add_parser("regression-plan", help="select local tests by affected Skill lineage")
    regression.add_argument("pack")
    regression.add_argument("--skill", action="append", required=True)
    regression.set_defaults(func=cmd_regression_plan)

    memory = commands.add_parser("memory", help="manage temporal Person Profile memory")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    subject = memory_commands.add_parser("subject")
    subject.add_argument("--workspace", default=".")
    subject.add_argument("--name", required=True)
    subject.add_argument("--relation", required=True)
    subject.add_argument("--access", default="private-local")
    subject.set_defaults(func=cmd_memory)
    fact = memory_commands.add_parser("fact")
    fact.add_argument("--workspace", default=".")
    fact.add_argument("--action", choices=("ADD", "UPDATE", "REVOKE"), required=True)
    fact.add_argument("--subject", required=True)
    fact.add_argument("--dimension", required=True)
    fact.add_argument("--statement", required=True)
    fact.add_argument("--confidence", type=float, required=True)
    fact.add_argument("--access", default="private-local")
    fact.add_argument("--supersedes")
    fact.set_defaults(func=cmd_memory)

    validate = commands.add_parser("validate", help="validate a Pack or Skill")
    validate.add_argument("target")
    validate.set_defaults(func=cmd_validate)

    test = commands.add_parser("test", help="score structure and aggregate independent results")
    test.add_argument("pack")
    test.add_argument("--results")
    test.set_defaults(func=cmd_test)

    install = commands.add_parser("install", help="install tested Skills with backup and read-back")
    install.add_argument("pack")
    install.add_argument("--target")
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--force", action="store_true")
    install.set_defaults(func=cmd_install)

    release = commands.add_parser("release", help="apply hard gates and complete test/ship phases")
    release.add_argument("pack")
    release.set_defaults(func=cmd_release)

    export = commands.add_parser("export", help="export a tested Pack")
    export.add_argument("pack")
    export.add_argument("--output", default="dist")
    export.add_argument("--runtime", default="generic")
    export.set_defaults(func=cmd_export)

    evolve = commands.add_parser("evolve", help="prepare a Darwin handoff")
    evolve.add_argument("pack")
    evolve.add_argument("--skill")
    evolve.add_argument("--comparisons")
    evolve.set_defaults(func=cmd_evolve)

    benchmark = commands.add_parser("benchmark", help="run a frozen Profile benchmark suite")
    benchmark.add_argument(
        "--suite",
        required=True,
    )
    benchmark.add_argument("--output")
    benchmark.set_defaults(func=cmd_benchmark)

    batch = commands.add_parser("batch", help="distill independent Packs concurrently")
    batch.add_argument("--manifest", required=True)
    batch.add_argument("--workspace", default=".")
    batch.add_argument("--workers", type=int, default=4)
    batch.set_defaults(func=cmd_batch)

    profiles = commands.add_parser("profiles", help="export built-in Profile templates")
    profiles.add_argument("--output", required=True)
    profiles.set_defaults(func=cmd_profiles)

    guide = commands.add_parser(
        "guide",
        help="run a recoverable guided distillation session before creating a Pack",
    )
    guide_commands = guide.add_subparsers(dest="guide_command", required=True)
    guide_init = guide_commands.add_parser("init", help="create a guided workspace")
    guide_init.add_argument("workspace")
    guide_init.add_argument("--subject", required=True)
    guide_init.add_argument("--object", dest="object_type", choices=GUIDE_OBJECTS, required=True)
    guide_init.add_argument(
        "--interaction-mode", choices=INTERACTION_MODES, default="hybrid"
    )
    guide_init.add_argument("--target-capability")
    guide_init.add_argument("--target-user")
    guide_init.add_argument("--output-goal")
    guide_init.add_argument(
        "--access",
        choices=("public", "authorized", "private-local"),
        default="private-local",
    )
    guide_init.add_argument("--consent", choices=CONSENT_LEVELS)
    guide_init.set_defaults(func=cmd_guide)

    guide_set = guide_commands.add_parser("set", help="refine scope and exclusions")
    guide_set.add_argument("workspace")
    guide_set.add_argument("--target-capability")
    guide_set.add_argument("--target-user")
    guide_set.add_argument("--output-goal")
    guide_set.add_argument("--exclude", action="append", default=[])
    guide_set.set_defaults(func=cmd_guide)

    guide_status = guide_commands.add_parser("status", help="show state and next questions")
    guide_status.add_argument("workspace")
    guide_status.set_defaults(func=cmd_guide)

    guide_record = guide_commands.add_parser(
        "record", help="record an answer, source, correction, gap, observation, or result"
    )
    guide_record.add_argument("workspace")
    guide_record.add_argument("--from", dest="from_file")
    guide_record.add_argument("--kind", choices=EVENT_KINDS)
    guide_record.add_argument("--content")
    guide_record.add_argument(
        "--evidence-class", choices=SESSION_EVIDENCE_CLASSES, default="unknown"
    )
    guide_record.add_argument("--permission", choices=("public", "authorized", "private-local", "unknown"), default="unknown")
    guide_record.add_argument("--locator")
    guide_record.add_argument("--notes")
    guide_record.set_defaults(func=cmd_guide)

    guide_confirm = guide_commands.add_parser(
        "confirm", help="confirm or reject a human checkpoint"
    )
    guide_confirm.add_argument("workspace")
    guide_confirm.add_argument("--checkpoint", choices=CHECKPOINTS, required=True)
    guide_confirm.add_argument("--status", choices=CHECKPOINT_STATUSES, required=True)
    guide_confirm.add_argument("--notes")
    guide_confirm.set_defaults(func=cmd_guide)

    guide_advance = guide_commands.add_parser("advance", help="pass the current stage gate")
    guide_advance.add_argument("workspace")
    guide_advance.set_defaults(func=cmd_guide)

    guide_export = guide_commands.add_parser(
        "export", help="export the evidence-graded session as a source"
    )
    guide_export.add_argument("workspace")
    guide_export.add_argument("--output")
    guide_export.set_defaults(func=cmd_guide)

    guide_pack = guide_commands.add_parser(
        "create-pack", help="create a formal Pack from the session and optional sources"
    )
    guide_pack.add_argument("workspace")
    guide_pack.add_argument("--source", action="append", default=[])
    guide_pack.add_argument("--mode", choices=MODES, default="standard")
    guide_pack.add_argument("--output", required=True)
    guide_pack.set_defaults(func=cmd_guide)

    postgres = commands.add_parser("postgres", help="initialize, migrate, and verify PostgreSQL")
    postgres_commands = postgres.add_subparsers(dest="postgres_command", required=True)
    postgres_init = postgres_commands.add_parser("init")
    postgres_init.add_argument(
        "--migration",
        default="migrations/postgres/001_initial.sql",
    )
    postgres_init.set_defaults(func=cmd_postgres)
    postgres_health = postgres_commands.add_parser("health")
    postgres_health.set_defaults(func=cmd_postgres)
    postgres_migrate = postgres_commands.add_parser("migrate")
    postgres_migrate.add_argument("--sqlite", required=True)
    postgres_migrate.add_argument("--batch-size", type=int, default=500)
    postgres_migrate.set_defaults(func=cmd_postgres)
    postgres_load = postgres_commands.add_parser("load-test")
    postgres_load.add_argument("--query", required=True)
    postgres_load.add_argument("--iterations", type=int, default=100)
    postgres_load.add_argument("--tenant", default="local")
    postgres_load.add_argument("--principal", default="local-user")
    postgres_load.set_defaults(func=cmd_postgres)

    recipe = commands.add_parser("recipe", help="evaluate and promote versioned Recipes")
    recipe_commands = recipe.add_subparsers(dest="recipe_command", required=True)
    recipe_list = recipe_commands.add_parser("list")
    recipe_list.add_argument("--workspace", default=".")
    recipe_list.set_defaults(func=cmd_recipe)
    recipe_evaluate = recipe_commands.add_parser("evaluate")
    recipe_evaluate.add_argument("--workspace", default=".")
    recipe_evaluate.add_argument("--baseline", required=True)
    recipe_evaluate.add_argument("--candidate", required=True)
    recipe_evaluate.add_argument("--budgets", required=True)
    recipe_evaluate.add_argument("--output")
    recipe_evaluate.set_defaults(func=cmd_recipe)
    recipe_promote = recipe_commands.add_parser("promote")
    recipe_promote.add_argument("--workspace", default=".")
    recipe_promote.add_argument("--recipe", required=True)
    recipe_promote.add_argument("--decision", required=True)
    recipe_promote.set_defaults(func=cmd_recipe)

    serve = commands.add_parser("serve", help="run authenticated HTTP API")
    serve.add_argument("--workspace", default=".")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=cmd_serve)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (
        DeliveryError,
        IngestionError,
        GuidedSessionError,
        ExperienceError,
        LearningError,
        PipelineError,
        ProviderError,
        SourceQualityError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"one: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
