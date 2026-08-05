"""Command-line interface for the complete one-skills workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from . import __version__
from .constants import MODES, OBJECT_TYPES, PHASES
from .database import KnowledgeDB
from .delivery import DeliveryError, export_pack, install_pack, prepare_darwin
from .evaluation import evaluate_pack
from .ingest import IngestionError
from .pipeline import (
    PipelineError,
    advance_phase,
    approve_and_compile,
    create_pack,
    init_workspace,
    load_state,
    workspace_for,
)
from .retrieval import HybridRetriever, local_embedding
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
        args.source,
        args.type,
        args.mode,
        args.name,
        args.access,
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


def cmd_advance(args: argparse.Namespace) -> int:
    state = advance_phase(_path(args.pack), args.phase, args.status, args.notes or "")
    _print({"current_phase": state["current_phase"], "phases": state["phases"]})
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    skill = approve_and_compile(_path(args.pack), args.candidate, args.reason)
    print(f"compiled Skill: {skill}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    workspace = workspace_for(_path(args.workspace))
    with KnowledgeDB(workspace / ".one" / "knowledge.db") as database:
        results = HybridRetriever(database).search(args.query, set(args.access), args.limit)
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
    findings = validate_pack(target) if (target / "PIPELINE_STATE.json").exists() else validate_skill(target)
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


def cmd_export(args: argparse.Namespace) -> int:
    archive = export_pack(_path(args.pack), _path(args.output))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="one", description="Evidence-first Skill distillation and knowledge system")
    parser.add_argument("--version", action="version", version=f"one-skills {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="initialize a workspace and SQLite knowledge base")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--mode", choices=MODES, default="standard")
    init.set_defaults(func=cmd_init)

    distill = commands.add_parser("distill", help="ingest, index, map, extract, and verify sources")
    distill.add_argument("--source", action="append", required=True)
    distill.add_argument("--workspace", default=".")
    distill.add_argument("--type", choices=OBJECT_TYPES, default="auto")
    distill.add_argument("--mode", choices=MODES, default="standard")
    distill.add_argument("--name")
    distill.add_argument("--access", choices=("public", "authorized", "private-local"), default="private-local")
    distill.set_defaults(func=cmd_distill)

    inspect = commands.add_parser("inspect", help="inspect Pack state")
    inspect.add_argument("pack")
    inspect.set_defaults(func=cmd_inspect)

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

    search = commands.add_parser("search", help="ACL-aware keyword, semantic, and graph retrieval")
    search.add_argument("query")
    search.add_argument("--workspace", default=".")
    search.add_argument("--access", action="append", default=["public"])
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)

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

    export = commands.add_parser("export", help="export a tested Pack")
    export.add_argument("pack")
    export.add_argument("--output", default="dist")
    export.set_defaults(func=cmd_export)

    evolve = commands.add_parser("evolve", help="prepare a Darwin handoff")
    evolve.add_argument("pack")
    evolve.add_argument("--skill")
    evolve.add_argument("--comparisons")
    evolve.set_defaults(func=cmd_evolve)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (
        DeliveryError,
        IngestionError,
        PipelineError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"one: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
