from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from one_skills.compilers import capability_from_verified_candidate
from one_skills.models import Candidate
from one_skills.overview import confirm_object_overview
from one_skills.pipeline import compile_confirmed_portfolio, create_pack
from one_skills.portfolio import build_portfolio, confirm_portfolio
from one_skills.validation import validate_skill

EXPECTED_TITLES = {
    "person": "证据化人物视角顾问",
    "content": "内容能力网络",
    "methodology": "证据化方法工具",
    "sop": "可恢复 SOP 工作流",
    "tool": "工具操作路由器",
    "skill": "Whole-folder Skill 修复器",
    "hybrid": "复合对象能力路由器",
}


class ProfileCompilerTests(unittest.TestCase):
    def _candidate(self, profile: str) -> Candidate:
        return Candidate(
            id=f"{profile}-module",
            title=f"{profile}-module",
            candidate_type="framework",
            summary="必须先确认输入和边界，再执行步骤并通过结果读回验证完成状态。",
            evidence_ids=[f"{profile}-evidence"],
            source_contexts=["source::A", "source::B"],
            source_ids=["source"],
            independence_groups=["group-a", "group-b"],
            cross_domain=True,
            source_independent=True,
            predictive=True,
            distinctive=True,
            actionable=True,
            status="accepted",
            problem=f"执行 {profile} 专属能力",
            assumptions=["输入和权限已确认"],
            mechanism=["按专属契约处理问题"],
            triggers=[f"明确请求 {profile} 能力"],
            anti_triggers=["纯信息查询"],
            inputs=["目标", "约束"],
            procedure=["确认前提", "执行专属流程", "验证结果"],
            output=f"{profile} 专属结果",
            done="结果已经读回并可复核",
            boundaries=["不扩大权限"],
            failures=["证据不足"],
            verification={
                "fallback": "停止并补证",
                "generated_name": f"{profile}-module",
            },
        )

    def test_all_profiles_compile_distinct_dual_layer_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for profile, expected_title in EXPECTED_TITLES.items():
                source = root / f"{profile}.md"
                source.write_text(
                    "# A\n\n必须先确认输入和边界，再执行并验证结果。\n\n"
                    "# B\n\n另一个场景也要求先确认约束，然后完成读回。",
                    encoding="utf-8",
                )
                pack = create_pack(
                    root / f"workspace-{profile}",
                    [str(source)],
                    profile,
                    "quick",
                    f"{profile}-pack",
                    "public",
                    "public-only" if profile == "person" else None,
                )
                confirm_object_overview(pack, "对象骨架已核对")
                build_portfolio(pack, [self._candidate(profile)], kind="verified")
                confirm_portfolio(pack, "保留一个 Profile 专属模块")
                report = compile_confirmed_portfolio(pack)
                self.assertEqual(report["modules"], 1)
                skill = pack / "skills" / f"{profile}-pack"
                text = (skill / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn(expected_title, text)
                self.assertIn("## 组合与依赖", text)
                self.assertIn("selected_module", text)
                self.assertIn("前置检查，不占辅助模块槽位", text)
                self.assertIn("退出不等于拒答", text)
                self.assertIn("用户明确要求的要素列成输出检查项", text)
                self.assertTrue(
                    (skill / "references" / "modules" / f"{profile}-module.md").exists()
                )
                self.assertTrue((pack / "CAPABILITY_GRAPH.json").exists())
                self.assertTrue((pack / "GLOSSARY.md").exists())
                self.assertTrue((pack / "DIGEST.md").exists())
                self.assertFalse(
                    [item for item in validate_skill(skill) if item.severity == "error"]
                )
                state = json.loads(
                    (pack / "PIPELINE_STATE.json").read_text(encoding="utf-8")
                )
                self.assertEqual(state["current_phase"], "test")

    def test_governance_disposition_compiles_as_governance_module(self) -> None:
        candidate = self._candidate("methodology")
        candidate.status = "needs_evidence"
        candidate.disposition = "governance"
        capability = capability_from_verified_candidate(candidate)
        self.assertEqual(capability.module_type, "governance")
        capability.validate()


if __name__ == "__main__":
    unittest.main()
