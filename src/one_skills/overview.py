"""Evidence-linked Object Overview generation and confirmation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .core_assets import (
    load_reproducibility,
    load_source_manifest,
    load_source_quality,
    save_reproducibility,
)
from .models import ObjectOverview
from .profiles import profile_prompt
from .provider import ModelProvider, ProviderError
from .utils import atomic_write, dump_json, load_json, stable_json_hash, utc_now


class OverviewError(ValueError):
    pass


def _compact_text(text: str, limit: int = 280) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip("，,；;：: ") + "…"


def _deterministic_overview(pack: Path) -> ObjectOverview:
    metadata = load_json(pack / "pack.json")
    chunks = load_json(pack / "sources" / "chunks.json")
    manifest = load_source_manifest(pack)
    profile = metadata["profile"]
    structure: list[dict[str, Any]] = []
    claims: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        claim_key = re.search(
            r"(?m)^Claim-Key:\s*([a-z0-9][a-z0-9-]{1,63})\s*$",
            chunk["text"],
        )
        statement = re.search(
            r"(?m)^Claim-Statement:\s*(.+?)\s*$",
            chunk["text"],
        )
        if not claim_key or not statement:
            continue
        key = claim_key.group(1)
        item = claims.setdefault(
            key,
            {
                "title": key,
                "summary": statement.group(1).strip(),
                "relation": "capability-candidate",
                "source_locators": [],
            },
        )
        if chunk["source_locator"] not in item["source_locators"]:
            item["source_locators"].append(chunk["source_locator"])
    if claims:
        structure = list(claims.values())
    seen: set[tuple[str, str]] = set()
    if not structure:
        for chunk in chunks:
            key = (chunk["document_id"], chunk["section_path"])
            if key in seen:
                continue
            seen.add(key)
            structure.append(
                {
                    "title": chunk["section_path"],
                    "summary": _compact_text(chunk["text"]),
                    "relation": "source-order",
                    "source_locators": [chunk["source_locator"]],
                }
            )
        structure = structure[:24]
    titles = [item["title"] for item in structure if item["title"]]
    key_terms = [
        {
            "term": title,
            "definition": item["summary"],
            "source_locator": item["source_locators"][0],
        }
        for title, item in zip(titles, structure)
        if item["source_locators"]
    ]
    selected_sources = manifest.get("sources", [])
    source_coverage = {
        item.get("title", item.get("source", "source")): list(item.get("chunk_ids", []))
        for item in selected_sources
    }
    limitations = [
        "当前 Overview 是由结构和来源元数据确定性生成的候选，需要人工或 Builder 语义确认。",
        "来源中出现的主张不自动证明方法在新场景中有效。",
    ]
    if any(chunk.get("source_role") == "counterevidence" for chunk in chunks):
        limitations.append("对象包含独立反证来源，不能只按支持性材料解释。")
    quality = load_source_quality(pack)
    subject = quality.get("subject") or metadata["name"]
    counterevidence = [
        f"{chunk['section_path']}：{_compact_text(chunk['text'], 180)}"
        for chunk in chunks
        if chunk.get("source_role") in {"counterevidence", "verification_anchor"}
        and chunk["section_path"] not in {"来源定位", "结构化主张：反馈完整性"}
    ][:4]
    return ObjectOverview(
        profile=profile,
        subject=subject,
        thesis=(
            f"从 {len(selected_sources)} 个冻结来源版本提炼“{subject}”中的"
            f"{len(structure)} 个候选能力骨架，并用独立反证、版本和权利边界约束迁移。"
        ),
        structure=structure or [
            {
                "title": metadata["name"],
                "summary": "来源没有可用章节结构。",
                "relation": "unknown",
                "source_locators": [],
            }
        ],
        key_terms=key_terms,
        mechanism_chain=titles,
        timeline_or_state_model=[
            "调查与证据",
            "形成阶段性判断",
            "返回实践与一线验证",
            "根据异常改判",
            "决定保持、扩展、收缩或停止",
        ],
        tensions=counterevidence,
        limitations=limitations,
        research_gaps=list(quality.get("gaps", [])),
        source_coverage=source_coverage,
    )


def _model_overview(pack: Path, provider: ModelProvider) -> ObjectOverview:
    metadata = load_json(pack / "pack.json")
    chunks = load_json(pack / "sources" / "chunks.json")
    payload_chunks = [
        {
            "id": item["id"],
            "section": item["section_path"],
            "locator": item["source_locator"],
            "source_role": item.get("source_role", "evidence"),
            "text": item["text"][:2000],
        }
        for item in chunks[:80]
    ]
    result = provider.complete_json(
        (
            "Build an evidence-linked Object Overview, not a summary. Return JSON with strings "
            "thesis; arrays structure, key_terms, mechanism_chain, timeline_or_state_model, "
            "tensions, limitations, research_gaps; object source_coverage. Every structure item "
            "must contain title, summary, relation, source_locators. Every key term must contain "
            "term, definition, source_locator. Use only supplied chunks and preserve conflicts."
        ),
        json.dumps(
            {
                "subject": metadata["name"],
                "profile_contract": profile_prompt(metadata["profile"]),
                "chunks": payload_chunks,
            },
            ensure_ascii=False,
        ),
        "object-overview",
    )
    required_arrays = (
        "structure",
        "key_terms",
        "mechanism_chain",
        "timeline_or_state_model",
        "tensions",
        "limitations",
        "research_gaps",
    )
    if not isinstance(result.get("thesis"), str) or any(
        not isinstance(result.get(field), list) for field in required_arrays
    ):
        raise ProviderError("object-overview response is incomplete")
    overview = ObjectOverview(
        profile=metadata["profile"],
        subject=metadata["name"],
        thesis=result["thesis"].strip(),
        structure=result["structure"],
        key_terms=result["key_terms"],
        mechanism_chain=result["mechanism_chain"],
        timeline_or_state_model=result["timeline_or_state_model"],
        tensions=result["tensions"],
        limitations=result["limitations"],
        research_gaps=result["research_gaps"],
        source_coverage=result.get("source_coverage", {}),
    )
    overview.validate()
    return overview


def render_overview(overview: dict[str, Any]) -> str:
    lines = [
        "# Object Overview",
        "",
        f"- Profile: `{overview['profile']}`",
        f"- Status: `{overview['status']}`",
        f"- Subject: {overview['subject']}",
        "",
        "## 一句话主旨",
        "",
        overview["thesis"],
        "",
        "## 对象骨架",
        "",
    ]
    for index, item in enumerate(overview["structure"], start=1):
        locators = "、".join(f"`{value}`" for value in item.get("source_locators", []))
        lines.append(
            f"{index}. **{item['title']}**：{item['summary']} "
            f"（关系：{item.get('relation', 'unknown')}；来源：{locators or '待补'}）"
        )
    lines.extend(["", "## 关键术语", "", "| 术语 | 对象内含义 | 来源 |", "|---|---|---|"])
    for item in overview["key_terms"]:
        lines.append(
            f"| {item.get('term', '')} | {item.get('definition', '')} | "
            f"`{item.get('source_locator', '')}` |"
        )
    for title, key in (
        ("机制或论证链", "mechanism_chain"),
        ("时间线或状态模型", "timeline_or_state_model"),
        ("内部张力", "tensions"),
        ("局限", "limitations"),
        ("研究缺口", "research_gaps"),
    ):
        lines.extend(["", f"## {title}", ""])
        values = overview.get(key, [])
        lines.extend(f"- {value}" for value in values)
        if not values:
            lines.append("- 无已确认条目。")
    lines.extend(
        [
            "",
            "> 此文件是 `OBJECT_OVERVIEW.json` 的人类可读投影；确认前不能作为发布事实。",
            "",
        ]
    )
    return "\n".join(lines)


def build_object_overview(
    pack: Path,
    provider: ModelProvider | None = None,
) -> dict[str, Any]:
    overview = _model_overview(pack, provider) if provider else _deterministic_overview(pack)
    value = overview.to_dict()
    dump_json(pack / "OBJECT_OVERVIEW.json", value)
    atomic_write(pack / "OBJECT_OVERVIEW.md", render_overview(value))
    overview_hash = stable_json_hash(value)
    metadata = load_json(pack / "pack.json")
    metadata["object_overview_hash"] = overview_hash
    metadata.setdefault("semantic_contract", {})["overview_confirmation"] = "pending"
    metadata["semantic_contract"].setdefault("capability_confirmation", "pending")
    dump_json(pack / "pack.json", metadata)
    constraints = load_reproducibility(pack)
    constraints["object_overview_hash"] = overview_hash
    save_reproducibility(pack, constraints)
    return value


def confirm_object_overview(pack: Path, notes: str) -> dict[str, Any]:
    if not notes.strip():
        raise OverviewError("Object Overview confirmation requires notes")
    path = pack / "OBJECT_OVERVIEW.json"
    if not path.exists():
        raise OverviewError("Object Overview does not exist")
    value = load_json(path)
    value["status"] = "confirmed"
    value["confirmed_at"] = utc_now()
    value["confirmation_notes"] = notes.strip()
    dump_json(path, value)
    atomic_write(pack / "OBJECT_OVERVIEW.md", render_overview(value))
    overview_hash = stable_json_hash(value)
    metadata = load_json(pack / "pack.json")
    metadata["object_overview_hash"] = overview_hash
    metadata.setdefault("semantic_contract", {})["overview_confirmation"] = "confirmed"
    dump_json(pack / "pack.json", metadata)
    constraints = load_reproducibility(pack)
    constraints["object_overview_hash"] = overview_hash
    save_reproducibility(pack, constraints)
    return value
