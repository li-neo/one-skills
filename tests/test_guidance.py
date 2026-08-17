from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from one_skills.guidance import recommend_next_action
from one_skills.overview import confirm_object_overview
from one_skills.pipeline import create_pack
from one_skills.utils import dump_json, load_json


MODEL_ENV = {
    "ONE_SKILLS_MODEL_BASE_URL": "http://127.0.0.1:11434/v1",
    "ONE_SKILLS_MODEL_API_KEY": "local",
    "ONE_SKILLS_MODEL": "qwen",
}

ISOLATED_MODEL_ENV = {
    "ONE_SKILLS_BUILDER_BASE_URL": "http://127.0.0.1:11434/v1",
    "ONE_SKILLS_BUILDER_API_KEY": "local",
    "ONE_SKILLS_BUILDER_MODEL": "builder",
    "ONE_SKILLS_ANSWER_BASE_URL": "http://127.0.0.1:11434/v1",
    "ONE_SKILLS_ANSWER_API_KEY": "local",
    "ONE_SKILLS_ANSWER_MODEL": "answer",
    "ONE_SKILLS_JUDGE_BASE_URL": "http://127.0.0.1:11434/v1",
    "ONE_SKILLS_JUDGE_API_KEY": "local",
    "ONE_SKILLS_JUDGE_MODEL": "judge",
}


class GuidanceTests(unittest.TestCase):
    def _pack(
        self,
        root: Path,
        *,
        access: str = "public",
        consent: str | None = None,
    ) -> Path:
        source = root / "method.md"
        source.write_text(
            "# Context A\n\n必须先确认事实，再运行可逆试验并检查结果。\n\n"
            "# Context B\n\n另一个场景也应该先确认事实，再运行试验。",
            encoding="utf-8",
        )
        return create_pack(
            root / "workspace",
            [str(source)],
            "person" if consent else "methodology",
            "quick",
            "guided-method",
            access,
            consent,
        )

    def test_initial_recommendation_is_executable_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            before = (pack / "pack.json").read_bytes()

            with patch.dict(os.environ, {}, clear=True):
                result = recommend_next_action(pack)
                executable = recommend_next_action(
                    pack,
                    confirmation_notes="对象结构与来源已核对",
                )

            self.assertEqual(result["action"], "confirm_overview")
            self.assertEqual(result["artifact_maturity"], "draft_unverified")
            self.assertIsNone(result["command"])
            self.assertIn("confirmation_notes", result["blocked_by"])
            self.assertIn(str(pack), executable["command"])
            self.assertIn("对象结构与来源已核对", executable["command"])
            self.assertEqual((pack / "pack.json").read_bytes(), before)

    def test_public_pack_requires_model_configuration_then_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            confirm_object_overview(pack, "对象骨架已核对")

            with patch.dict(os.environ, {}, clear=True):
                missing = recommend_next_action(pack)
            self.assertEqual(missing["action"], "configure_model")
            self.assertEqual(missing["command"], "one model status")
            self.assertEqual(missing["blocked_by"], ["model_configuration"])

            with patch.dict(os.environ, MODEL_ENV, clear=True):
                ready = recommend_next_action(pack)
            self.assertEqual(ready["action"], "verify_with_model")
            self.assertIn(f"one verify-model {pack}", ready["command"])
            self.assertNotIn("--allow-sensitive-data", ready["command"])

    def test_non_public_pack_requires_endpoint_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(
                Path(temporary),
                access="authorized",
                consent="self",
            )
            confirm_object_overview(pack, "本人已核对对象骨架")

            with patch.dict(os.environ, MODEL_ENV, clear=True):
                blocked = recommend_next_action(pack)
                authorized = recommend_next_action(
                    pack,
                    allow_sensitive_data=True,
                )

            self.assertEqual(blocked["action"], "authorize_sensitive_data")
            self.assertIsNone(blocked["command"])
            self.assertEqual(
                blocked["blocked_by"],
                ["sensitive_data_authorization"],
            )
            self.assertEqual(
                {item["network_scope"] for item in blocked["endpoints"]},
                {"local"},
            )
            self.assertEqual(authorized["action"], "verify_with_model")
            self.assertIn("--allow-sensitive-data", authorized["command"])

    def test_verified_portfolio_is_confirmed_before_compile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            confirm_object_overview(pack, "对象骨架已核对")
            decisions_path = pack / "verified" / "decisions.json"
            decisions = load_json(decisions_path)
            self.assertTrue(decisions)
            decisions[0]["status"] = "accepted"
            decisions[0]["predictive"] = True
            dump_json(decisions_path, decisions)
            audit = {
                "generated_at": "2026-08-17T00:00:00+00:00",
                "records": [{"candidate_id": decisions[0]["id"], "accepted": True}],
            }
            dump_json(pack / "audit" / "model-verification.json", audit)

            result = recommend_next_action(
                pack,
                confirmation_notes="能力组合已核对",
            )

            self.assertEqual(result["action"], "confirm_portfolio")
            self.assertIn("--artifact portfolio", result["command"])
            self.assertEqual(
                result["artifact_maturity"],
                "verified_unconfirmed",
            )

    def test_evaluation_inputs_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            metadata_path = pack / "pack.json"
            metadata = load_json(metadata_path)
            metadata["semantic_contract"]["overview_confirmation"] = "confirmed"
            metadata["semantic_contract"]["capability_confirmation"] = "confirmed"
            metadata["lifecycle"]["phases"]["verify"]["status"] = "completed"
            metadata["lifecycle"]["phases"]["compile"]["status"] = "completed"
            metadata["lifecycle"]["phases"]["link"]["status"] = "completed"
            metadata["lifecycle"]["phases"]["test"]["status"] = "in_progress"
            metadata["lifecycle"]["current_phase"] = "test"
            dump_json(metadata_path, metadata)
            skill = pack / "skills" / "guided-method"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            suite = Path(temporary) / "suite.json"
            suite.write_text("{}\n", encoding="utf-8")

            missing = recommend_next_action(pack)
            supplied = recommend_next_action(
                pack,
                suite_path=suite,
            )

            self.assertEqual(missing["action"], "freeze_evaluation_suite")
            self.assertIsNone(missing["command"])
            self.assertEqual(missing["blocked_by"], ["evaluation_suite_path"])
            self.assertIn(f"--suite {suite.resolve()}", supplied["command"])

    def test_non_public_comparison_requires_fresh_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(
                Path(temporary),
                access="authorized",
                consent="self",
            )
            metadata_path = pack / "pack.json"
            metadata = load_json(metadata_path)
            metadata["semantic_contract"]["overview_confirmation"] = "confirmed"
            metadata["semantic_contract"]["capability_confirmation"] = "confirmed"
            metadata["lifecycle"]["phases"]["verify"]["status"] = "completed"
            metadata["lifecycle"]["phases"]["compile"]["status"] = "completed"
            metadata["lifecycle"]["phases"]["link"]["status"] = "completed"
            metadata["lifecycle"]["phases"]["test"]["status"] = "in_progress"
            metadata["lifecycle"]["current_phase"] = "test"
            dump_json(metadata_path, metadata)
            skill = pack / "skills" / "guided-method"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            evaluations = pack / "evaluations"
            evaluations.mkdir()
            (evaluations / "suite.json").write_text("{}\n", encoding="utf-8")
            baseline = Path(temporary) / "baseline.json"
            baseline.write_text("{}\n", encoding="utf-8")

            with patch.dict(os.environ, ISOLATED_MODEL_ENV, clear=True):
                blocked = recommend_next_action(pack, baseline_path=baseline)
                authorized = recommend_next_action(
                    pack,
                    allow_sensitive_data=True,
                    baseline_path=baseline,
                )

            self.assertEqual(blocked["action"], "authorize_sensitive_data")
            self.assertIsNone(blocked["command"])
            self.assertEqual(authorized["action"], "run_comparison")
            self.assertIn("--allow-sensitive-data", authorized["command"])

    def test_stale_comparison_is_rerun_instead_of_released(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            metadata_path = pack / "pack.json"
            metadata = load_json(metadata_path)
            metadata["semantic_contract"]["overview_confirmation"] = "confirmed"
            metadata["semantic_contract"]["capability_confirmation"] = "confirmed"
            metadata["lifecycle"]["phases"]["verify"]["status"] = "completed"
            metadata["lifecycle"]["phases"]["compile"]["status"] = "completed"
            metadata["lifecycle"]["phases"]["link"]["status"] = "completed"
            metadata["lifecycle"]["phases"]["test"]["status"] = "in_progress"
            metadata["lifecycle"]["current_phase"] = "test"
            dump_json(metadata_path, metadata)
            skill = pack / "skills" / "guided-method"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            evaluations = pack / "evaluations"
            evaluations.mkdir()
            (evaluations / "suite.json").write_text("{}\n", encoding="utf-8")
            dump_json(
                evaluations / "comparison-report.json",
                {"status": "stale", "passed": True},
            )
            baseline = Path(temporary) / "baseline.json"
            baseline.write_text("{}\n", encoding="utf-8")

            with patch.dict(os.environ, ISOLATED_MODEL_ENV, clear=True):
                result = recommend_next_action(pack, baseline_path=baseline)

            self.assertEqual(result["action"], "run_comparison")
            self.assertIn("one compare run", result["command"])
            self.assertTrue(
                any("stale" in warning for warning in result["warnings"])
            )


if __name__ == "__main__":
    unittest.main()
