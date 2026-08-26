from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from one_skills.constants import OBJECT_TO_PROFILE, OBJECT_TYPES
from one_skills.pipeline import create_pack


class ObjectTypeTests(unittest.TestCase):
    def test_core_object_types_are_first_class(self) -> None:
        for object_type in (
            "auto",
            "content",
            "methodology",
            "sop",
            "tool",
            "skill",
            "hybrid",
        ):
            self.assertIn(object_type, OBJECT_TYPES)

    def test_alias_object_types_still_route_to_shared_profiles(self) -> None:
        for object_type in ("customer", "proposal", "thought-system"):
            self.assertIn(object_type, OBJECT_TO_PROFILE)

    def test_canonical_mapping(self) -> None:
        self.assertEqual(OBJECT_TO_PROFILE["customer"], "hybrid")
        self.assertEqual(OBJECT_TO_PROFILE["proposal"], "content")
        self.assertEqual(OBJECT_TO_PROFILE["thought-system"], "hybrid")

    def test_routing_and_guided_share_canonical_map(self) -> None:
        from one_skills.guided import PROFILE_BY_GUIDE_OBJECT
        from one_skills.routing import OBJECT_TO_PROFILE as routing_map

        self.assertIs(routing_map, OBJECT_TO_PROFILE)
        self.assertIs(PROFILE_BY_GUIDE_OBJECT, OBJECT_TO_PROFILE)

    def test_distill_mapping_produces_valid_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "method.md"
            source.write_text(
                "# 方案\n\n目标、假设、决策分支、结果。\n\n# 客户\n\n诉求、异议、决策。",
                encoding="utf-8",
            )
            for object_type in ("customer", "proposal", "thought-system"):
                profile = OBJECT_TO_PROFILE[object_type]
                pack = create_pack(
                    root / f"workspace-{object_type}",
                    [str(source)],
                    profile,
                    "quick",
                    f"pack-{object_type}",
                    "public",
                    None,
                )
                self.assertTrue((pack / "pack.json").exists())


if __name__ == "__main__":
    unittest.main()
