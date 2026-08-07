"""Human-readable projections of the v0.3 semantic IR."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .learning import build_learning_path
from .models import Candidate, Capability
from .utils import atomic_write, load_json


def _module_path(pack: Path, capability: Capability) -> str:
    metadata = load_json(pack / "pack.json")
    return (
        f"skills/{metadata['slug']}/references/modules/"
        f"{capability.id}.md"
    )


def render_index(
    pack: Path,
    graph: dict[str, Any],
    capabilities: list[Capability],
    candidates: list[Candidate],
) -> str:
    metadata = load_json(pack / "pack.json")
    by_id = {item.id: item for item in candidates}
    lines = [
        f"# {metadata['name']} — Capability Index",
        "",
        f"> Profile: `{metadata['profile']}` · Pack schema: `{metadata['schema_version']}`",
        "",
        "## 阅读入口",
        "",
        "- [Object Overview](OBJECT_OVERVIEW.md)",
        "- [Candidate Portfolio](CANDIDATE_PORTFOLIO.md)",
        "- [Verified Portfolio](VERIFIED_PORTFOLIO.md)",
        "- [Glossary](GLOSSARY.md)",
        "- [Digest](DIGEST.md)",
        "- [Learning Path](LEARNING_PATH.json)",
        f"- [Runtime Skill](skills/{metadata['slug']}/SKILL.md)",
        "",
        "## 能力模块",
        "",
    ]
    grouped: dict[str, list[Capability]] = {}
    for capability in capabilities:
        candidate = by_id.get(capability.id)
        group = candidate.candidate_type if candidate else "capability"
        grouped.setdefault(group, []).append(capability)
    for group, values in grouped.items():
        lines.extend([f"### {group}", ""])
        for capability in values:
            lines.append(
                f"- [{capability.name}]({_module_path(pack, capability)})："
                f"{capability.problem}（状态：`{capability.status}`）"
            )
        lines.append("")
    lines.extend(["## 能力关系图", "", "```mermaid", "flowchart TD"])
    for node in graph["nodes"]:
        if node["type"] in {"capability", "governance"}:
            title = str(node["title"]).replace('"', "'")
            lines.append(f'    {node["id"].replace("-", "_")}["{title}"]')
    for edge in graph["edges"]:
        if edge["from_type"] not in {"capability", "governance"}:
            continue
        if edge["to_type"] not in {"capability", "governance"}:
            continue
        left = edge["from_id"].replace("-", "_")
        right = edge["to_id"].replace("-", "_")
        lines.append(f"    {left} -->|{edge['relation']}| {right}")
    lines.extend(
        [
            "```",
            "",
            "## 推荐学习顺序",
            "",
        ]
    )
    learning = load_json(pack / "LEARNING_PATH.json") if (pack / "LEARNING_PATH.json").exists() else {}
    for node in sorted(learning.get("nodes", []), key=lambda item: item["order"]):
        lines.append(
            f"{node['order'] + 1}. **{node['title']}**"
            f"（先修：{', '.join(node['prerequisites']) or '无'}）"
        )
    lines.extend(
        [
            "",
            "## 状态纪律",
            "",
            "- `candidate` 只表示已生成且可审计，不表示真实任务有效。",
            "- 只有完整 Answer Agent/Judge 结果和发布硬门通过后才能安装。",
            "",
        ]
    )
    return "\n".join(lines)


def render_glossary(pack: Path, candidates: list[Candidate]) -> str:
    terms = [
        item
        for item in candidates
        if item.disposition == "term" or item.candidate_type in {"term", "glossary"}
    ]
    lines = [
        "# Glossary",
        "",
        "| 术语 | 对象内含义 | Evidence IDs |",
        "|---|---|---|",
    ]
    for item in terms:
        lines.append(
            f"| {item.title} | {item.summary} | "
            f"{', '.join(f'`{value}`' for value in item.evidence_ids)} |"
        )
    if not terms:
        overview = load_json(pack / "OBJECT_OVERVIEW.json")
        for item in overview.get("key_terms", []):
            lines.append(
                f"| {item.get('term', '')} | {item.get('definition', '')} | "
                f"`{item.get('source_locator', '')}` |"
            )
    if len(lines) == 4:
        lines.append("| 暂无独立术语 | 术语候选尚未通过 Portfolio 整理 | |")
    lines.append("")
    return "\n".join(lines)


def render_digest(
    pack: Path,
    capabilities: list[Capability],
    candidates: list[Candidate],
) -> str:
    overview = load_json(pack / "OBJECT_OVERVIEW.json")
    lines = [
        f"# {overview['subject']} — Digest",
        "",
        "> 只呈现 Capability Portfolio 中保留的能力；不是原材料摘要。",
        "",
        "## 对象在解决什么问题",
        "",
        overview["thesis"],
        "",
    ]
    for capability in capabilities:
        lines.extend(
            [
                f"## {capability.name}",
                "",
                f"**解决的问题**：{capability.problem}",
                "",
                f"**何时使用**：{capability.trigger}",
                "",
                "**核心机制**：",
                "",
                *[f"- {step}" for step in capability.procedure],
                "",
                "**什么时候会失效**：",
                "",
                *[f"- {value}" for value in [*capability.boundaries, *capability.failures]],
                "",
                f"→ [运行模块]({_module_path(pack, capability)})",
                "",
            ]
        )
    counterexamples = [
        item
        for item in candidates
        if item.disposition == "counterexample"
    ]
    lines.extend(["## 反例与陷阱", ""])
    lines.extend(f"- **{item.title}**：{item.summary}" for item in counterexamples)
    if not counterexamples:
        lines.append("- 反例候选尚未形成独立条目；以各模块失败条件为准。")
    lines.extend(["", "## 来源局限", ""])
    lines.extend(f"- {item}" for item in overview.get("limitations", []))
    lines.append("")
    return "\n".join(lines)


def write_semantic_artifacts(
    pack: Path,
    graph: dict[str, Any],
    capabilities: list[Capability],
    candidates: list[Candidate],
) -> None:
    build_learning_path(pack)
    atomic_write(pack / "INDEX.md", render_index(pack, graph, capabilities, candidates))
    atomic_write(pack / "GLOSSARY.md", render_glossary(pack, candidates))
    atomic_write(pack / "DIGEST.md", render_digest(pack, capabilities, candidates))
