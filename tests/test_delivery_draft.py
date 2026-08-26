from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from one_skills.delivery import DeliveryError, _assert_installable, release_pack
from one_skills.pipeline import create_pack
from one_skills.utils import dump_json, load_json


class DraftReleaseTests(unittest.TestCase):
    def _pack(self, root: Path, mode: str) -> Path:
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
            f"draft-{mode}",
            "public",
            None,
        )

    def test_draft_release_rejects_stable_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary), "standard")
            with self.assertRaises(DeliveryError) as context:
                release_pack(pack, draft=True)
            self.assertIn("only valid for quick or continuous", str(context.exception))

    def test_draft_release_requires_test_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary), "quick")
            with self.assertRaises(DeliveryError) as context:
                release_pack(pack, draft=True)
            self.assertIn("requires current phase test", str(context.exception))

    def test_draft_tier_skips_comparison_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary), "quick")
            metadata = load_json(pack / "pack.json")
            metadata["release_tier"] = "draft"
            dump_json(pack / "pack.json", metadata)

            # Draft tier: no blind comparison report, yet installable.
            _assert_installable(pack)

    def test_stable_tier_still_requires_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary), "quick")
            # No release_tier means stable; no comparison report must fail.
            with self.assertRaises(DeliveryError):
                _assert_installable(pack)


if __name__ == "__main__":
    unittest.main()
