"""Object routing and profile-specific extraction contracts."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
import re

from .models import SourceDocument


@dataclass(frozen=True)
class Profile:
    name: str
    map_dimensions: tuple[str, ...]
    candidate_kinds: tuple[str, ...]
    required_boundaries: tuple[str, ...]
    compiler: str


PROFILES = {
    "person": Profile(
        "person",
        ("timeline", "domains", "decisions", "view_changes", "expression", "tensions"),
        ("mental_model", "heuristic", "value", "anti_pattern", "expression_pattern"),
        ("consent", "sensitive_inference", "identity_impersonation"),
        "perspective-router",
    ),
    "content": Profile(
        "content",
        ("thesis", "structure", "concepts", "arguments", "cases", "counterexamples"),
        ("framework", "principle", "case", "counterexample", "term"),
        ("source_limit", "author_bias", "copyright"),
        "atomic-network",
    ),
    "methodology": Profile(
        "methodology",
        ("goal", "assumptions", "mechanism", "steps", "branches", "failure_conditions"),
        ("framework", "principle", "case", "counterexample", "term"),
        ("preconditions", "misuse", "invalid_context"),
        "atomic-network",
    ),
    "sop": Profile(
        "sop",
        ("roles", "preconditions", "systems", "states", "exceptions", "handoffs"),
        ("procedure", "decision", "failure", "verification", "term"),
        ("authorization", "destructive_action", "incomplete_cleanup"),
        "workflow",
    ),
    "tool": Profile(
        "tool",
        ("capabilities", "contracts", "state", "auth", "side_effects", "errors"),
        ("operation", "contract", "failure", "verification", "term"),
        ("credential", "side_effect", "version"),
        "operation-router",
    ),
    "skill": Profile(
        "skill",
        ("purpose", "triggers", "workflow", "resources", "tests", "defects"),
        ("capability", "trigger", "failure", "test", "term"),
        ("purpose_drift", "trigger_conflict", "test_deletion"),
        "skill-repair",
    ),
    "hybrid": Profile(
        "hybrid",
        ("objects", "roles", "knowledge", "tools", "workflow", "constraints"),
        ("capability", "procedure", "case", "counterexample", "term"),
        ("cross_object_permission", "conflicting_source", "orchestration"),
        "router",
    ),
}
_LOADED_PLUGIN_ENTRIES: set[str] = set()


def register_profile(profile: Profile, replace: bool = False) -> None:
    if profile.name in PROFILES and not replace:
        raise ValueError(f"profile already registered: {profile.name}")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", profile.name):
        raise ValueError("profile name must be hyphen-case")
    PROFILES[profile.name] = profile


def load_profile_plugins() -> list[str]:
    loaded: list[str] = []
    discovered = entry_points()
    selected = (
        discovered.select(group="one_skills.profiles")
        if hasattr(discovered, "select")
        else discovered.get("one_skills.profiles", [])
    )
    for entry_point in selected:
        identity = f"{entry_point.name}:{entry_point.value}"
        if identity in _LOADED_PLUGIN_ENTRIES:
            continue
        value = entry_point.load()
        profile = value() if callable(value) else value
        if not isinstance(profile, Profile):
            raise TypeError(f"profile plugin {entry_point.name} did not return Profile")
        register_profile(profile)
        _LOADED_PLUGIN_ENTRIES.add(identity)
        loaded.append(profile.name)
    return loaded


def detect_profile(documents: list[SourceDocument], source_values: list[str]) -> str:
    paths = [
        Path(value).expanduser()
        for value in source_values
        if not value.startswith(("http://", "https://"))
    ]
    if any(path.is_dir() and (path / "SKILL.md").exists() for path in paths):
        return "skill"
    sample = "\n".join(document.text[:20000] for document in documents).lower()
    names = " ".join(document.title.lower() for document in documents)
    scores = {name: 0 for name in PROFILES}
    signals = {
        "person": ("访谈", "我认为", "他说", "她说", "biography", "interview", "career"),
        "content": ("目录", "前言", "chapter", "序言", "作者", "课程", "podcast"),
        "methodology": ("框架", "方法论", "原则", "模型", "framework", "methodology"),
        "sop": ("标准作业", "操作步骤", "审批", "交接", "升级路径", "runbook", "procedure"),
        "tool": ('"openapi"', '"swagger"', "endpoint", "api reference", "authentication"),
        "skill": ("---\nname:", "should_trigger", "test-prompts", "agent skill"),
        "hybrid": ("组织", "角色", "系统", "流程", "案例库"),
    }
    for profile, tokens in signals.items():
        scores[profile] += sum(sample.count(token) for token in tokens)
    if any(token in names for token in ("openapi", "swagger", "api")):
        scores["tool"] += 5
    if any(path.name == "SKILL.md" for path in paths):
        scores["skill"] += 10
    if any(path.suffix.lower() == ".epub" for path in paths):
        scores["content"] += 5
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] == 0:
        return "content"
    if len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.8 and ranked[1][1] >= 3:
        return "hybrid"
    return ranked[0][0]


def profile_prompt(profile_name: str) -> str:
    profile = PROFILES[profile_name]
    dimensions = ", ".join(profile.map_dimensions)
    kinds = ", ".join(profile.candidate_kinds)
    boundaries = ", ".join(profile.required_boundaries)
    return (
        f"Profile: {profile.name}\n"
        f"Map dimensions: {dimensions}\n"
        f"Extract candidates: {kinds}\n"
        f"Required boundaries: {boundaries}\n"
        "Every claim must cite an exact source locator. Separate quotation, interpretation, "
        "and model inference. Preserve contradictions and rejected candidates."
    )


def signal_patterns(profile_name: str) -> dict[str, re.Pattern[str]]:
    common = {
        "framework": re.compile(
            r"(框架|模型|方法|先.+再|如果.+那么|framework|model|method|step)", re.I
        ),
        "principle": re.compile(
            r"(原则|必须|应该|不要|只有|规则|清单|principle|must|should|never)", re.I
        ),
        "case": re.compile(r"(例如|比如|案例|曾经|当时|结果|for example|case)", re.I),
        "counterexample": re.compile(
            r"(失败|错误|陷阱|风险|例外|避免|不能|failure|mistake|risk)", re.I
        ),
        "term": re.compile(r"(.{1,30})(是指|定义为|意味着|称为|refers to|means)", re.I),
    }
    if profile_name == "sop":
        common["framework"] = re.compile(
            r"(步骤|执行|输入|输出|完成标准|审批|回滚|step|run|verify)", re.I
        )
    elif profile_name == "person":
        common["framework"] = re.compile(
            r"(我会|我通常|判断|决定|看重|反对|习惯|I believe|I decide)", re.I
        )
    elif profile_name == "tool":
        common["framework"] = re.compile(
            r"(endpoint|request|response|parameter|认证|权限|调用|返回)", re.I
        )
    elif profile_name == "skill":
        common["framework"] = re.compile(
            r"(触发|工作流|步骤|边界|失败|trigger|workflow|fallback)", re.I
        )
    return common
