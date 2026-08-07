"""Profile-specific semantic contracts for the v0.3 distillation plane."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileSpec:
    name: str
    overview_sections: tuple[str, ...]
    extractor_views: tuple[str, ...]
    compiler: str
    relation_types: tuple[str, ...]
    learning_policy: str
    evaluation_types: tuple[str, ...]
    module_strategy: str = "single"


COMMON_EVALUATIONS = (
    "should_trigger",
    "should_not_trigger",
    "edge_case",
    "sibling_bait",
    "failure",
    "safety",
    "task_effect",
)

COMMON_RELATIONS = (
    "depends_on",
    "contrasts_with",
    "composes_with",
    "invalidates",
)


PROFILE_SPECS = {
    "person": ProfileSpec(
        name="person",
        overview_sections=(
            "thesis",
            "domains",
            "timeline",
            "key_terms",
            "decision_patterns",
            "tensions",
            "limitations",
            "research_gaps",
        ),
        extractor_views=(
            "writings",
            "conversations",
            "decisions",
            "timeline",
            "external_views",
            "expression",
        ),
        compiler="person-perspective-router",
        relation_types=COMMON_RELATIONS,
        learning_policy="mental-model-prerequisite",
        evaluation_types=COMMON_EVALUATIONS + ("fidelity", "out_of_scope_honesty"),
        module_strategy="router-with-mental-models",
    ),
    "content": ProfileSpec(
        name="content",
        overview_sections=(
            "thesis",
            "structure",
            "key_terms",
            "argument_chain",
            "tensions",
            "limitations",
            "research_gaps",
        ),
        extractor_views=(
            "framework",
            "principle",
            "case",
            "counterexample",
            "glossary",
        ),
        compiler="content-atomic-network",
        relation_types=COMMON_RELATIONS,
        learning_policy="capability-prerequisite",
        evaluation_types=COMMON_EVALUATIONS + ("citation", "learning_transfer"),
        module_strategy="explicit-router-with-internal-modules",
    ),
    "methodology": ProfileSpec(
        name="methodology",
        overview_sections=(
            "goal",
            "assumptions",
            "mechanism_chain",
            "branches",
            "failure_conditions",
            "tensions",
            "limitations",
            "research_gaps",
        ),
        extractor_views=(
            "assumptions",
            "mechanism",
            "branches",
            "applications",
            "failures",
        ),
        compiler="methodology-atomic-network",
        relation_types=COMMON_RELATIONS,
        learning_policy="capability-prerequisite",
        evaluation_types=COMMON_EVALUATIONS + ("predictive_transfer", "citation"),
        module_strategy="explicit-router-with-internal-modules",
    ),
    "sop": ProfileSpec(
        name="sop",
        overview_sections=(
            "purpose",
            "roles",
            "preconditions",
            "state_model",
            "handoffs",
            "exceptions",
            "research_gaps",
        ),
        extractor_views=(
            "roles",
            "preconditions",
            "steps",
            "exceptions",
            "handoffs",
            "verification",
        ),
        compiler="sop-state-workflow",
        relation_types=COMMON_RELATIONS + ("hands_off_to", "rolls_back_to"),
        learning_policy="workflow-state-order",
        evaluation_types=COMMON_EVALUATIONS + ("readback", "rollback"),
        module_strategy="router-with-workflow-states",
    ),
    "tool": ProfileSpec(
        name="tool",
        overview_sections=(
            "purpose",
            "operations",
            "contracts",
            "auth",
            "side_effects",
            "errors",
            "research_gaps",
        ),
        extractor_views=(
            "operations",
            "contracts",
            "auth",
            "side_effects",
            "errors",
            "readback",
        ),
        compiler="tool-operation-router",
        relation_types=COMMON_RELATIONS + ("reads", "writes", "verifies"),
        learning_policy="operation-prerequisite",
        evaluation_types=COMMON_EVALUATIONS + ("schema", "side_effect", "readback"),
        module_strategy="router-with-operations",
    ),
    "skill": ProfileSpec(
        name="skill",
        overview_sections=(
            "purpose",
            "triggers",
            "workflow",
            "resources",
            "tests",
            "defects",
            "research_gaps",
        ),
        extractor_views=(
            "purpose",
            "triggers",
            "workflow",
            "resources",
            "tests",
            "defects",
        ),
        compiler="whole-folder-skill-repair",
        relation_types=COMMON_RELATIONS + ("shadows", "supersedes"),
        learning_policy="defect-to-repair",
        evaluation_types=COMMON_EVALUATIONS + ("baseline_delta", "regression"),
        module_strategy="whole-folder",
    ),
    "hybrid": ProfileSpec(
        name="hybrid",
        overview_sections=(
            "objects",
            "roles",
            "permissions",
            "knowledge",
            "tools",
            "orchestration",
            "conflicts",
            "research_gaps",
        ),
        extractor_views=(
            "objects",
            "permissions",
            "knowledge",
            "tools",
            "orchestration",
            "conflicts",
        ),
        compiler="hybrid-object-router",
        relation_types=COMMON_RELATIONS + ("routes_to", "hands_off_to"),
        learning_policy="subobject-prerequisite",
        evaluation_types=COMMON_EVALUATIONS + ("authorization", "orchestration"),
        module_strategy="router-with-subprofiles",
    ),
}


def profile_spec(name: str) -> ProfileSpec:
    try:
        return PROFILE_SPECS[name]
    except KeyError as exc:
        raise ValueError(f"unknown ProfileSpec: {name}") from exc
