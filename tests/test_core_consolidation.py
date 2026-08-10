from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from one_skills.core_assets import (
    load_pack_metadata,
    load_source_manifest,
)
from one_skills.distillation_quality import assess_distillation_quality
from one_skills.lifecycle import load_state
from one_skills.migrations import migrate_pack_to_v04
from one_skills.pipeline import create_pack
from one_skills.utils import dump_json
from one_skills.validation import validate_pack


class CoreConsolidationTests(unittest.TestCase):
    def _pack(self, root: Path) -> Path:
        source = root / "source.md"
        source.write_text(
            "# Method\n\n必须先确认事实和边界，再执行可逆试验并复核结果。",
            encoding="utf-8",
        )
        return create_pack(
            root / "workspace",
            [str(source)],
            "methodology",
            "quick",
            "core-pack",
            "public",
        )

    def test_new_pack_uses_consolidated_authoritative_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            metadata = load_pack_metadata(pack)
            self.assertEqual(metadata["schema_version"], "0.4")
            self.assertEqual(load_state(pack), metadata["lifecycle"])
            self.assertIn("quality", load_source_manifest(pack))
            for legacy in (
                "PIPELINE_STATE.json",
                "PIPELINE_STATE.md",
                "RECIPE_LOCK.json",
                "PROTECTED_CONSTRAINTS.json",
                "SOURCE_QUALITY.json",
                "OBJECT_MAP.md",
            ):
                self.assertFalse((pack / legacy).exists())

    def test_v03_pack_migrates_without_semantic_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            metadata = load_pack_metadata(pack)
            lifecycle = metadata.pop("lifecycle")
            recipe_lock = metadata.pop("recipe_lock")
            reproducibility = metadata.pop("reproducibility")
            metadata["schema_version"] = "0.3"
            dump_json(pack / "pack.json", metadata)
            dump_json(pack / "PIPELINE_STATE.json", lifecycle)
            dump_json(pack / "RECIPE_LOCK.json", recipe_lock)
            dump_json(pack / "PROTECTED_CONSTRAINTS.json", reproducibility)

            manifest = load_source_manifest(pack)
            quality = manifest.pop("quality")
            dump_json(pack / "SOURCE_MANIFEST.json", manifest)
            dump_json(pack / "SOURCE_QUALITY.json", quality)
            (pack / "PIPELINE_STATE.md").write_text("legacy projection\n", encoding="utf-8")
            (pack / "OBJECT_MAP.md").write_text("legacy projection\n", encoding="utf-8")

            report = migrate_pack_to_v04(pack)
            self.assertEqual(report["schema_version"], "0.4")
            self.assertEqual(len(report["removed_legacy_assets"]), 6)
            self.assertEqual(load_pack_metadata(pack)["lifecycle"], lifecycle)
            self.assertEqual(load_source_manifest(pack)["quality"], quality)
            self.assertFalse(
                [item for item in validate_pack(pack) if item.severity == "error"]
            )

    def test_released_mao_pack_passes_core_quality_gates(self) -> None:
        root = Path(__file__).resolve().parents[1]
        report = assess_distillation_quality(root / "packs" / "mao-methods")
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["dimensions"],
            {"reliability": 1.0, "completeness": 1.0, "accuracy": 1.0},
        )


if __name__ == "__main__":
    unittest.main()
