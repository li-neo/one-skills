"""Versioned distillation recipes and non-compensating promotion gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .profiles import PROFILES
from .utils import dump_json, load_json, utc_now


@dataclass(frozen=True)
class Recipe:
    id: str
    version: str
    profile: str
    parser: str
    chunker: str
    extractors: tuple[str, ...]
    verifier: str
    builder: str


def default_recipes() -> dict[str, Recipe]:
    return {
        profile: Recipe(
            id=f"{profile}-standard",
            version="2.0.0",
            profile=profile,
            parser="structural-text@2.0.0",
            chunker="semantic-section@2.0.0",
            extractors=(
                definition.spec.extractor_views
                if definition.spec
                else definition.candidate_kinds
            ),
            verifier="portfolio-v1-v2-v3@2.0.0",
            builder=f"{definition.spec.compiler if definition.spec else definition.compiler}@2.0.0",
        )
        for profile, definition in PROFILES.items()
    }


def initialize_registry(path: Path) -> None:
    defaults = default_recipes()
    if path.exists():
        registry = load_json(path)
        changed = False
        for name, recipe in defaults.items():
            active = registry["active"].get(name)
            if active != asdict(recipe):
                if active:
                    registry.setdefault("history", []).append(
                        {
                            "profile": name,
                            "previous": active,
                            "promoted_at": utc_now(),
                            "decision": {
                                "promote": True,
                                "reason": "built-in v0.3 semantic contract upgrade",
                            },
                        }
                    )
                registry["active"][name] = asdict(recipe)
                changed = True
        if changed:
            registry["updated_at"] = utc_now()
            dump_json(path, registry)
    else:
        dump_json(
            path,
            {
                "schema_version": "1.0",
                "updated_at": utc_now(),
                "active": {name: asdict(recipe) for name, recipe in defaults.items()},
                "history": [],
            },
        )


def promotion_decision(
    baseline: dict[str, float],
    candidate: dict[str, float],
    budgets: dict[str, float],
) -> dict[str, Any]:
    required = {
        "task_success",
        "false_trigger_rate",
        "evidence_coverage",
        "citation_accuracy",
        "safety_rate",
        "cost",
        "latency",
    }
    missing = required - baseline.keys() | required - candidate.keys()
    if missing:
        raise ValueError(f"recipe metrics missing: {', '.join(sorted(missing))}")
    gates = {
        "task_success_improved": candidate["task_success"] > baseline["task_success"],
        "false_triggers_not_worse": candidate["false_trigger_rate"] <= baseline["false_trigger_rate"],
        "evidence_not_worse": candidate["evidence_coverage"] >= baseline["evidence_coverage"],
        "citations_not_worse": candidate["citation_accuracy"] >= baseline["citation_accuracy"],
        "safety_perfect": candidate["safety_rate"] == 1.0,
        "cost_within_budget": candidate["cost"] <= budgets["cost"],
        "latency_within_budget": candidate["latency"] <= budgets["latency"],
    }
    return {"promote": all(gates.values()), "gates": gates}


def promote_recipe(
    registry_path: Path,
    recipe: Recipe,
    decision: dict[str, Any],
) -> None:
    if not decision.get("promote"):
        raise ValueError("recipe failed one or more non-compensating gates")
    initialize_registry(registry_path)
    registry = load_json(registry_path)
    previous = registry["active"].get(recipe.profile)
    registry["history"].append(
        {
            "profile": recipe.profile,
            "previous": previous,
            "promoted_at": utc_now(),
            "decision": decision,
        }
    )
    registry["active"][recipe.profile] = asdict(recipe)
    registry["updated_at"] = utc_now()
    dump_json(registry_path, registry)
