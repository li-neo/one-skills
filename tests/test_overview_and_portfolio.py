from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from one_skills.extraction import extract_structured_claims
from one_skills.models import Chunk
from one_skills.overview import confirm_object_overview
from one_skills.pipeline import create_pack, verify_pack_with_roles
from one_skills.portfolio import confirm_portfolio


class FakeRoleProvider:
    def __init__(self, role: str):
        self.role = role

    def complete_json(self, system: str, user: str, schema_name: str) -> dict:
        del system
        payload = json.loads(user)
        if schema_name.startswith("extract-"):
            if schema_name != "extract-assumptions":
                return {"candidates": []}
            chunks = payload["chunks"]
            return {
                "candidates": [
                    {
                        "title": "investigate-before-scaling",
                        "summary": "必须先收集不同处境的一手事实，再用可逆试验检查当前判断。",
                        "tags": ["investigation"],
                        "problem": "结论建立在转述和单一样本上",
                        "assumptions": ["允许接触不同处境的一线角色"],
                        "mechanism": ["一手材料修正先验", "试验结果再次改判"],
                        "triggers": ["报告与一线反馈冲突"],
                        "anti_triggers": ["已有充分事实的低风险选择"],
                        "inputs": ["当前判断", "一手材料"],
                        "procedure": ["定义改判证据", "分开调查", "运行可逆试验"],
                        "output": "假设修订与试验结果",
                        "done": "结果足以支持保持或改判",
                        "boundaries": ["不得用调查之名强迫表态"],
                        "failures": ["样本被权力关系污染"],
                        "counterexamples": ["所有受访者在上级面前一致支持"],
                        "evidence": [
                            {"chunk_id": item["id"], "quote": item["text"]}
                            for item in chunks[:2]
                        ],
                    }
                ]
            }
        if schema_name == "candidate-transfer-answer":
            return {
                "novel_question": "新产品是否应直接全面推广？",
                "derived_answer": "先调查不同用户并用小范围试验验证。",
                "assumptions": "试点可撤回且不会造成不可逆损害。",
                "falsifier": "不同样本和试点结果持续支持直接推广。",
            }
        if schema_name == "candidate-transfer-judge":
            return {
                "cross_domain": True,
                "predictive": True,
                "distinctive": True,
                "actionable": True,
                "boundary": True,
                "reason": "回答给出可证伪、可执行且有边界的新场景迁移。",
            }
        if schema_name == "capability-ir":
            return {
                "name": "investigate-before-scaling",
                "problem": "在证据不足时避免全面推广",
                "trigger": "当结论依赖转述或单一样本时",
                "inputs": ["当前判断", "一手材料"],
                "procedure": ["定义改判证据", "分开调查", "运行可逆试验"],
                "output": "假设修订与试验结果",
                "done": "结果足以支持保持或改判",
                "boundaries": ["不得强迫表态"],
                "failures": ["样本污染"],
                "fallback": "缩小试点并补充独立样本",
            }
        raise AssertionError(f"unexpected schema: {schema_name}")


class FakeRoles:
    isolation_level = "model-shared/session-separated"

    def providers(self) -> dict[str, FakeRoleProvider]:
        return {
            "builder": FakeRoleProvider("builder"),
            "answer": FakeRoleProvider("answer"),
            "judge": FakeRoleProvider("judge"),
        }


class OverviewAndPortfolioTests(unittest.TestCase):
    def test_multiple_structured_claims_in_one_chunk(self) -> None:
        chunk = Chunk(
            id="chunk-1",
            document_id="document-1",
            document_version=1,
            section_path="Claims",
            ordinal=0,
            text=(
                "Claim-Key: first-claim\n"
                "Claim-Statement: 必须先调查不同角色，再根据反证修正判断。\n"
                "Claim-Type: framework\n"
                "Evidence: 第一条可核验证据支持调查和改判。\n\n"
                "Claim-Key: second-claim\n"
                "Claim-Statement: 方案必须经过小范围试验，并预先设置停止条件。\n"
                "Claim-Type: principle\n"
                "Evidence: 第二条可核验证据支持试验和停止条件。\n"
            ),
            content_hash="1" * 64,
            access_level="public",
            source_locator="source#L1",
            source_key="source",
            independence_group="group",
        )
        candidates, evidence = extract_structured_claims([chunk], "methodology")
        self.assertEqual({item.title for item in candidates}, {"first-claim", "second-claim"})
        self.assertEqual(len(evidence), 2)

    def test_role_separated_verification_stops_at_portfolio_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "method.md"
            source.write_text(
                "# Context A\n\n必须先调查不同角色，再根据反证修正判断。\n\n"
                "# Context B\n\n面对新场景应该先取得一手材料，再运行可逆试验。",
                encoding="utf-8",
            )
            pack = create_pack(
                root / "workspace",
                [str(source)],
                "methodology",
                "deep",
                "method",
                "public",
            )
            confirm_object_overview(pack, "对象骨架与来源定位正确")
            report = verify_pack_with_roles(pack, FakeRoles())
            self.assertEqual(report["accepted"], 1)
            self.assertEqual(report["portfolio_status"], "candidate")
            portfolio = confirm_portfolio(pack, "保留一个原子调查模块")
            self.assertEqual(portfolio["status"], "confirmed")
            metadata = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
            self.assertEqual(
                metadata["semantic_contract"]["capability_confirmation"],
                "confirmed",
            )


if __name__ == "__main__":
    unittest.main()
