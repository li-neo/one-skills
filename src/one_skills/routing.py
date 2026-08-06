"""Explainable, abstaining object router for distillation intake."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

OBJECT_TO_PROFILE = {
    "person": "person",
    "customer": "hybrid",
    "proposal": "hybrid",
    "skill": "skill",
    "methodology": "methodology",
    "thought-system": "hybrid",
    "book": "content",
    "document": "content",
    "sop": "sop",
    "tool": "tool",
}

SIGNALS = {
    "person": (
        (r"人物|名人|伟人|老板|同事|家人|自己|思维方式|视角|毛泽东|鲁迅|芒格", 4),
        (r"person|biography|perspective|how .+ thinks", 4),
    ),
    "customer": ((r"客户|用户画像|customer", 4),),
    "proposal": ((r"方案|提案|proposal|pitch", 4),),
    "skill": (
        (
            r"(?:现有|已有|这个|修复|优化|审查).{0,8}(?:skill|技能)"
            r"|SKILL\.md|skill本身",
            4,
        ),
    ),
    "methodology": ((r"方法论|方法体系|框架|methodology|framework", 4),),
    "thought-system": ((r"思想体系|理论体系|哲学体系|thought system", 4),),
    "book": ((r"书籍|一本书|拆书|选集|文集|book|epub", 4),),
    "document": ((r"文档|报告|论文|课程|视频|播客|document|paper|course", 3),),
    "sop": ((r"\bSOP\b|标准作业|操作流程|runbook|procedure", 5),),
    "tool": ((r"工具|API|软件|命令行|tool|sdk|openapi", 4),),
}


def route_intent(intent: str, sources: list[str] | None = None) -> dict[str, Any]:
    minimal_intent = intent.strip()
    if not minimal_intent:
        raise ValueError("routing intent must not be empty")
    scores = {name: 0 for name in OBJECT_TO_PROFILE}
    matched: dict[str, list[dict[str, Any]]] = {name: [] for name in scores}
    for object_type, patterns in SIGNALS.items():
        for pattern, weight in patterns:
            if re.search(pattern, minimal_intent, re.IGNORECASE):
                scores[object_type] += weight
                matched[object_type].append(
                    {"rule": pattern, "weight": weight, "origin": "intent"}
                )
    source_kinds: list[str] = []
    for value in sources or []:
        path = Path(value)
        suffix = path.suffix.lower()
        if path.name == "SKILL.md" or (path.is_dir() and (path / "SKILL.md").exists()):
            scores["skill"] += 6
            matched["skill"].append(
                {"rule": "skill-directory", "weight": 6, "origin": "source"}
            )
            source_kinds.append("skill")
        elif suffix == ".epub":
            scores["book"] += 5
            source_kinds.append("book")
        elif suffix in {".pdf", ".md", ".txt", ".docx", ".html"}:
            scores["document"] += 2
            source_kinds.append("document")
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    top_type, top_score = ranked[0]
    second_score = ranked[1][1]
    margin = top_score - second_score
    needs_confirmation = top_score < 3 or margin < 2
    selected = None if needs_confirmation else top_type
    if selected in {"person", "customer", "proposal", "thought-system"}:
        recommended_path = "guided"
    elif selected:
        recommended_path = "direct_pack" if sources else "guided"
    else:
        recommended_path = "confirm"
    candidates = [
        {
            "object_type": object_type,
            "profile": OBJECT_TO_PROFILE[object_type],
            "score": score,
            "signals": matched[object_type],
        }
        for object_type, score in ranked[:3]
        if score > 0
    ]
    questions = []
    if needs_confirmation:
        questions = [
            "你要蒸馏的是人物本人、其著作内容，还是可迁移的方法论？",
            "首期要交付一个视角 Skill、多个原子 Skills，还是学习课程？",
        ]
    return {
        "schema_version": "1.0",
        "selected_object_type": selected,
        "selected_profile": OBJECT_TO_PROFILE.get(selected) if selected else None,
        "routing_score": top_score,
        "margin": margin,
        "confidence_band": (
            "abstain"
            if needs_confirmation
            else "high"
            if top_score >= 6 and margin >= 3
            else "medium"
        ),
        "needs_confirmation": needs_confirmation,
        "recommended_path": recommended_path,
        "candidates": candidates,
        "source_kinds": sorted(set(source_kinds)),
        "next_questions": questions,
        "privacy": "raw intent and source contents are not persisted by the router",
    }
