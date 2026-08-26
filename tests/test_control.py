from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from one_skills.control import build_control_status
from one_skills.errors import PipelineError
from one_skills.guided import init_session
from one_skills.lifecycle import init_workspace
from one_skills.pipeline import create_pack


class ControlStatusTests(unittest.TestCase):
    def _pack(self, root: Path, mode: str = "quick") -> Path:
        source = root / "method.md"
        source.write_text(
            "# A\n\n先确认事实，再运行可逆试验。\n\n# B\n\n另一场景同样先确认事实。",
            encoding="utf-8",
        )
        return create_pack(
            root / "workspace",
            [str(source)],
            "methodology",
            mode,
            "ctrl-method",
            "public",
            None,
        )

    def test_workspace_status_lists_packs_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = init_workspace(Path(temporary) / "ws")
            status = build_control_status(root)
            self.assertEqual(status["asset_kind"], "workspace")
            self.assertEqual(status["active_controller"], "none")
            self.assertIn("distill", status["allowed_actions"])
            self.assertIn("packs", status["details"])

    def test_pack_status_returns_stable_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            status = build_control_status(pack)
            self.assertEqual(status["schema_version"], "1.0")
            self.assertEqual(status["asset_kind"], "pack")
            self.assertEqual(status["active_controller"], "pack")
            self.assertIn(status["current_stage"], {
                "contract", "ingest", "map", "extract", "verify",
            })
            self.assertIsInstance(status["ready_to_advance"], bool)
            self.assertIsInstance(status["allowed_actions"], list)
            self.assertIn("status", status["allowed_actions"])
            self.assertIn("recommended_action", status)
            self.assertIn("gate", status)
            # Every phase has itemized checks.
            self.assertEqual(
                set(status["gate"]),
                {
                    "contract", "ingest", "map", "extract", "verify",
                    "compile", "link", "test", "ship", "evolve",
                },
            )

    def test_pack_status_gate_is_itemized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            status = build_control_status(pack)
            contract_checks = status["gate"]["contract"]
            self.assertTrue(contract_checks)
            for check in contract_checks:
                self.assertEqual(set(check), {"id", "passed", "detail"})
                self.assertIsInstance(check["passed"], bool)

    def test_guided_status_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "g"
            init_session(workspace, "评审者", "methodology")
            blocked = build_control_status(workspace)
            self.assertEqual(blocked["asset_kind"], "guided_session")
            self.assertEqual(blocked["active_controller"], "guided")
            self.assertFalse(blocked["ready_to_advance"])
            self.assertEqual(blocked["blocker_code"], "target_capability")

    def test_status_rejects_unknown_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(PipelineError):
            build_control_status(Path(temporary) / "missing")


if __name__ == "__main__":
    unittest.main()
