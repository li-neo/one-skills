from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from one_skills.evolution import (
    EvolutionError,
    apply_patch_candidate,
    propose_patch,
    resolve_patch,
    skill_folder_hash,
)
from one_skills.experience import record_experience


class EvolutionPatchTests(unittest.TestCase):
    @staticmethod
    def _passing_comparison() -> dict:
        return {
            "before_score": 0.5,
            "after_score": 0.8,
            "hard_gates": {
                "source_facts": True,
                "authorization": True,
                "safety": True,
                "canonical_evals": True,
                "negative_tests": True,
            },
        }

    def test_recurrence_gate_apply_and_revert(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            skill = pack / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("# Before\n", encoding="utf-8")
            first = record_experience(
                pack,
                "demo",
                "missing rollback",
                "corrected",
                "first failure",
                "run:1",
                "add rollback",
                "public",
            )
            second = record_experience(
                pack,
                "demo",
                "missing rollback",
                "failure",
                "second failure",
                "run:2",
                access="public",
            )
            before_hash = skill_folder_hash(pack)
            patch = propose_patch(
                pack,
                "UPDATE",
                "skills/demo/SKILL.md",
                "# After\n\nRollback is mandatory.\n",
                [first["id"], second["id"]],
                "task_effect",
            )
            applied = apply_patch_candidate(
                pack,
                patch["id"],
                self._passing_comparison(),
            )
            self.assertEqual(applied["status"], "applied")
            self.assertIn("Rollback", skill.read_text(encoding="utf-8"))
            resolved = resolve_patch(
                pack,
                patch["id"],
                "revert",
                "holdout exposed a regression",
            )
            self.assertEqual(resolved["status"], "reverted")
            self.assertEqual(skill_folder_hash(pack), before_hash)
            self.assertEqual(skill.read_text(encoding="utf-8"), "# Before\n")

    def test_evaluation_events_and_frozen_tests_cannot_drive_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            target = pack / "skills" / "demo" / "SKILL.md"
            target.parent.mkdir(parents=True)
            target.write_text("# Demo\n", encoding="utf-8")
            heldout = record_experience(
                pack,
                "demo",
                "hidden",
                "failure",
                "holdout",
                "eval:1",
                access="public",
                scope="evaluation",
            )
            with self.assertRaises(EvolutionError):
                propose_patch(
                    pack,
                    "UPDATE",
                    "skills/demo/SKILL.md",
                    "# Changed\n",
                    [heldout["id"], "missing"],
                    "task_effect",
                )

    def test_tampered_patch_id_cannot_escape_snapshot_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = root / "pack"
            target = pack / "skills" / "demo" / "SKILL.md"
            target.parent.mkdir(parents=True)
            target.write_text("# Before\n", encoding="utf-8")
            first = record_experience(
                pack, "demo", "failure", "failure", "one", "run:1", access="public"
            )
            second = record_experience(
                pack, "demo", "failure", "failure", "two", "run:2", access="public"
            )
            patch = propose_patch(
                pack,
                "UPDATE",
                "skills/demo/SKILL.md",
                "# After\n",
                [first["id"], second["id"]],
                "task_effect",
            )
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel"
            sentinel.write_text("keep", encoding="utf-8")
            proposal = (
                pack / "evolution" / "proposals" / f"{patch['id']}.json"
            )
            value = json.loads(proposal.read_text(encoding="utf-8"))
            value["id"] = str(outside)
            proposal.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaises(EvolutionError):
                apply_patch_candidate(
                    pack,
                    patch["id"],
                    self._passing_comparison(),
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_empty_hard_gates_cannot_apply_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            target = pack / "skills" / "demo" / "SKILL.md"
            target.parent.mkdir(parents=True)
            target.write_text("# Before\n", encoding="utf-8")
            first = record_experience(
                pack, "demo", "failure", "failure", "one", "run:1", access="public"
            )
            second = record_experience(
                pack, "demo", "failure", "failure", "two", "run:2", access="public"
            )
            patch = propose_patch(
                pack,
                "UPDATE",
                "skills/demo/SKILL.md",
                "# After\n",
                [first["id"], second["id"]],
                "task_effect",
            )
            with self.assertRaises(EvolutionError):
                apply_patch_candidate(
                    pack,
                    patch["id"],
                    {"before_score": 0.5, "after_score": 0.8, "hard_gates": {}},
                )
            self.assertEqual(target.read_text(encoding="utf-8"), "# Before\n")

    def test_revert_rejects_drift_before_restoring_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            target = pack / "skills" / "demo" / "SKILL.md"
            sibling = pack / "skills" / "other" / "SKILL.md"
            target.parent.mkdir(parents=True)
            sibling.parent.mkdir(parents=True)
            target.write_text("# Before\n", encoding="utf-8")
            sibling.write_text("# Original\n", encoding="utf-8")
            first = record_experience(
                pack, "demo", "failure", "failure", "one", "run:1", access="public"
            )
            second = record_experience(
                pack, "demo", "failure", "failure", "two", "run:2", access="public"
            )
            patch = propose_patch(
                pack,
                "UPDATE",
                "skills/demo/SKILL.md",
                "# After\n",
                [first["id"], second["id"]],
                "task_effect",
            )
            apply_patch_candidate(pack, patch["id"], self._passing_comparison())
            sibling.write_text("# Drift\n", encoding="utf-8")

            with self.assertRaises(EvolutionError):
                resolve_patch(pack, patch["id"], "revert", "rollback")
            self.assertEqual(target.read_text(encoding="utf-8"), "# After\n")


if __name__ == "__main__":
    unittest.main()
