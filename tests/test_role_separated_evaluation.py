from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from one_skills.comparison import compare_runs, local_skill_context, run_condition
from one_skills.delivery import DeliveryError, _assert_tested
from one_skills.models import Candidate
from one_skills.overview import confirm_object_overview
from one_skills.pipeline import compile_confirmed_portfolio, create_pack
from one_skills.portfolio import build_portfolio, confirm_portfolio


class FakeEvaluationProvider:
    def __init__(self, role: str):
        self.role = role

    def complete_json(self, system: str, user: str, schema_name: str) -> dict:
        del system
        import json

        payload = json.loads(user)
        if schema_name == "blind-skill-answer":
            good = "GOOD-SKILL" in payload["skill_context"]
            return {
                "answer": "GOOD grounded reversible answer" if good else "generic answer",
                "selected_module": "module" if good else "",
                "would_trigger": good,
                "citations": ["https://example.org/source#section"] if good else [],
            }
        if schema_name == "blind-skill-judge":
            good = "GOOD grounded" in payload["anonymous_answer"]["answer"]
            return {
                "passed": good,
                "scores": {
                    "task_effect": 1.0 if good else 0.4,
                    "routing": 1.0 if good else 0.5,
                    "evidence": 1.0 if good else 0.2,
                    "safety": 1.0,
                    "learning": 1.0 if good else 0.4,
                    "citation_resolution": 1.0 if good else 0.0,
                    "citation_support": 1.0 if good else 0.0,
                },
                "reason": "candidate follows the rubric" if good else "generic response",
            }
        raise AssertionError(schema_name)


class FakeRoles:
    builder = SimpleNamespace(model="builder")
    answer = SimpleNamespace(model="answer")
    judge = SimpleNamespace(model="judge")
    isolation_level = "model-separated"

    def providers(self):
        return {
            "builder": FakeEvaluationProvider("builder"),
            "answer": FakeEvaluationProvider("answer"),
            "judge": FakeEvaluationProvider("judge"),
        }


class RoleSeparatedEvaluationTests(unittest.TestCase):
    def _compiled_pack(self, root: Path) -> Path:
        source = root / "source.md"
        source.write_text(
            "# A\n\n必须先确认事实和边界，再执行可逆试验。\n\n"
            "# B\n\n另一个场景也要求验证结果并保留回滚。",
            encoding="utf-8",
        )
        pack = create_pack(
            root / "workspace",
            [str(source)],
            "methodology",
            "quick",
            "eval-method",
            "public",
        )
        confirm_object_overview(pack, "对象骨架已确认")
        candidate = Candidate(
            id="module",
            title="module",
            candidate_type="framework",
            summary="必须先确认事实和边界，再执行可逆试验并验证结果。",
            evidence_ids=["ev-1"],
            source_contexts=["A", "B"],
            source_ids=["source"],
            independence_groups=["g1", "g2"],
            cross_domain=True,
            source_independent=True,
            predictive=True,
            distinctive=True,
            actionable=True,
            status="accepted",
            problem="证据不足时设计可逆试验",
            triggers=["明确调用本方法"],
            anti_triggers=["普通查询"],
            inputs=["事实"],
            procedure=["确认事实", "执行试验", "读回结果"],
            output="试验结论",
            done="结果可复核",
            boundaries=["不得不可逆扩大"],
            failures=["证据不足"],
            verification={"fallback": "补证", "generated_name": "module"},
        )
        build_portfolio(pack, [candidate], kind="verified")
        confirm_portfolio(pack, "保留模块")
        compile_confirmed_portfolio(pack)
        return pack

    def test_complete_records_and_non_compensating_comparison(self) -> None:
        suite = {
            "schema_version": "1.0",
            "cases": [
                {"id": "task", "type": "task_effect", "prompt": "task", "rubric": "do task"},
                {"id": "negative", "type": "should_not_trigger", "prompt": "lookup", "rubric": "abstain"},
                {"id": "sibling", "type": "sibling_bait", "prompt": "sibling", "rubric": "route"},
                {"id": "safety", "type": "safety", "prompt": "unsafe", "rubric": "refuse"},
                {"id": "citation", "type": "citation", "prompt": "cite", "rubric": "cite"},
                {"id": "holdout", "type": "holdout", "prompt": "ood", "rubric": "reason"},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._compiled_pack(Path(temporary))
            roles = FakeRoles()
            skill_path = next((pack / "skills").glob("*/SKILL.md"))
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8")
                + "\nGOOD-SKILL https://example.org/source#section\n",
                encoding="utf-8",
            )
            no_skill = run_condition(pack, suite, "no-skill", "", roles, "A")
            baseline = run_condition(pack, suite, "cangjie", "BASELINE", roles, "B")
            candidate = run_condition(
                pack,
                suite,
                "one-skills",
                local_skill_context(pack),
                roles,
                "C",
            )
            manifest = {
                "score_weights": {
                    "task_effect": 50,
                    "routing": 15,
                    "evidence": 10,
                    "safety": 15,
                    "learning": 5,
                    "cost": 5,
                },
                "win_rule": {"minimum_weighted_lead": 5.0},
            }
            report = compare_runs(pack, no_skill, baseline, candidate, manifest)
            self.assertTrue(report["passed"])
            self.assertGreaterEqual(report["weighted_lead"], 5)
            self.assertTrue(all(report["hard_gates"].values()))
            self.assertTrue((pack / "test-results.json").exists())
            self.assertEqual(len(candidate["records"]), 6)
            self.assertTrue(all(item["answer"] for item in candidate["records"]))
            self.assertTrue(all(item["judge_reason"] for item in candidate["records"]))
            _assert_tested(pack)
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8") + "\nSTALE\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DeliveryError, "current Skill context"):
                _assert_tested(pack)


if __name__ == "__main__":
    unittest.main()
