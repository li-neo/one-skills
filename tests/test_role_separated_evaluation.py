from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from one_skills.comparison import (
    COMPARISON_WEIGHTS,
    COMPARISON_WIN_RULE,
    ComparisonError,
    compare_runs,
    freeze_evaluation_suite,
    holdout_leaked_to_builder,
    local_skill_context,
    run_condition,
)
from one_skills.delivery import DeliveryError, _assert_tested
from one_skills.evaluation_state import mark_evaluations_stale
from one_skills.models import Candidate
from one_skills.overview import confirm_object_overview
from one_skills.pipeline import compile_confirmed_portfolio, create_pack
from one_skills.portfolio import build_portfolio, confirm_portfolio
from one_skills.utils import dump_json, load_json, stable_json_hash


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
        ledger = pack / "EVIDENCE_LEDGER.jsonl"
        lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            evidence_id = json.loads(lines[0])["id"]
        else:
            evidence_id = "ev-1"
            ledger.write_text(
                json.dumps(
                    {
                        "id": evidence_id,
                        "claim": "必须先确认事实和边界，再执行可逆试验。",
                        "evidence_type": "quote",
                        "source": "source",
                        "locator": "source.md#L1",
                        "confidence": 0.9,
                        "inference_level": "none",
                        "permission": "public",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        candidate = Candidate(
            id="module",
            title="module",
            candidate_type="framework",
            summary="必须先确认事实和边界，再执行可逆试验并验证结果。",
            evidence_ids=[evidence_id],
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
            with self.assertRaisesRegex(ComparisonError, "not the frozen"):
                run_condition(pack, suite, "no-skill", "", roles, "A")
            freeze_evaluation_suite(pack, suite)
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
                "score_weights": COMPARISON_WEIGHTS,
                "win_rule": COMPARISON_WIN_RULE,
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
            run_path = pack / "evaluations" / "runs" / "one-skills.json"
            report_path = pack / "evaluations" / "comparison-report.json"
            original_run = load_json(run_path)
            original_report = load_json(report_path)
            baseline_path = pack / "evaluations" / "runs" / "cangjie.json"
            original_baseline = load_json(baseline_path)
            tampered_baseline = load_json(baseline_path)
            tampered_baseline["records"][0]["answer"] += " tampered"
            dump_json(baseline_path, tampered_baseline)
            with self.assertRaisesRegex(DeliveryError, "cangjie evaluation run"):
                _assert_tested(pack)
            dump_json(baseline_path, original_baseline)

            tampered_report = load_json(report_path)
            tampered_report["passed"] = True
            tampered_report["hard_gates"]["safety_rate"] = False
            tampered_report["weighted_lead"] = -999.0
            dump_json(report_path, tampered_report)
            with self.assertRaisesRegex(
                DeliveryError,
                "conclusion does not match",
            ):
                _assert_tested(pack)
            dump_json(report_path, original_report)

            shared_run = load_json(run_path)
            shared_run["isolation_level"] = "model-shared/session-separated"
            shared_run["roles"]["judge"] = shared_run["roles"]["answer"]
            for record in shared_run["records"]:
                record["judge_model"] = shared_run["roles"]["judge"]
                record["isolation_level"] = shared_run["isolation_level"]
            shared_run.pop("artifact_hash")
            shared_run["artifact_hash"] = stable_json_hash(shared_run)
            shared_report = load_json(report_path)
            shared_report["isolation_level"] = shared_run["isolation_level"]
            shared_report["candidate_run_hash"] = shared_run["artifact_hash"]
            shared_report["run_hashes"]["one-skills"] = shared_run[
                "artifact_hash"
            ]
            dump_json(run_path, shared_run)
            dump_json(report_path, shared_report)
            with self.assertRaisesRegex(DeliveryError, "stable release requires"):
                _assert_tested(pack)
            dump_json(run_path, original_run)
            dump_json(report_path, original_report)

            manifest_path = pack / "SOURCE_MANIFEST.json"
            original_manifest = load_json(manifest_path)
            changed_manifest = load_json(manifest_path)
            changed_manifest["sources"][0]["active"] = False
            dump_json(manifest_path, changed_manifest)
            with self.assertRaisesRegex(DeliveryError, "current Source Set"):
                _assert_tested(pack)
            dump_json(manifest_path, original_manifest)

            skill_path.write_text(
                skill_path.read_text(encoding="utf-8") + "\nSTALE\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DeliveryError, "current Skill context"):
                _assert_tested(pack)
            mark_evaluations_stale(pack, "source set changed")
            self.assertEqual(load_json(report_path)["status"], "stale")
            with self.assertRaisesRegex(DeliveryError, "report is stale"):
                _assert_tested(pack)

    def test_non_public_skill_context_requires_explicit_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._compiled_pack(Path(temporary))
            metadata_path = pack / "pack.json"
            metadata = load_json(metadata_path)
            metadata["access_level"] = "authorized"
            dump_json(metadata_path, metadata)

            with self.assertRaisesRegex(
                ComparisonError,
                "--allow-sensitive-data",
            ):
                run_condition(
                    pack,
                    {},
                    "one-skills",
                    local_skill_context(pack),
                    FakeRoles(),
                    "A",
                )

    def test_holdout_rubric_leakage_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._compiled_pack(Path(temporary))
            skill_path = next((pack / "skills").glob("*/SKILL.md"))
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8")
                + "\nUNIQUE-HOLDOUT-RUBRIC\n",
                encoding="utf-8",
            )
            suite = {
                "cases": [
                    {
                        "id": "holdout",
                        "type": "holdout",
                        "prompt": "unseen prompt",
                        "rubric": "UNIQUE-HOLDOUT-RUBRIC",
                    }
                ]
            }
            self.assertTrue(holdout_leaked_to_builder(pack, suite))


if __name__ == "__main__":
    unittest.main()
