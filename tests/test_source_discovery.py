from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from one_skills.overview import confirm_object_overview
from one_skills.pipeline import create_pack
from one_skills.source_discovery import (
    SourceDiscoveryError,
    discover_sources,
    shortlist_sources,
)
from one_skills.validation import validate_pack


class SourceDiscoveryAndOverviewTests(unittest.TestCase):
    def test_local_discovery_is_candidate_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "method.md"
            source.write_text("# Method\n\n先调查，再试验。", encoding="utf-8")
            result = discover_sources(
                "local",
                str(root),
                "method",
                ["how it works"],
            )
            self.assertEqual(result["adapter"], "local")
            self.assertEqual(len(result["candidates"]), 1)
            self.assertEqual(result["candidates"][0]["status"], "candidate")
            self.assertNotIn("authority", result["candidates"][0])

            path = root / "candidates.json"
            path.write_text(json.dumps(result), encoding="utf-8")
            shortlisted = shortlist_sources(
                path,
                [result["candidates"][0]["id"]],
            )
            self.assertEqual(
                shortlisted["candidates"][0]["status"],
                "shortlisted",
            )
            with self.assertRaises(SourceDiscoveryError):
                shortlist_sources(path, ["missing"])

    def test_v03_pack_has_evidence_linked_overview_and_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "method.md"
            source.write_text(
                "# Investigation\n\n必须先调查具体事实，再设计小范围试验。\n\n"
                "# Review\n\n如果结果与判断冲突，应该记录反证并改判。",
                encoding="utf-8",
            )
            pack = create_pack(
                root / "workspace",
                [str(source)],
                "methodology",
                "quick",
                "method",
                "public",
            )
            metadata = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
            overview = json.loads(
                (pack / "OBJECT_OVERVIEW.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["schema_version"], "0.3")
            self.assertEqual(overview["status"], "candidate")
            self.assertTrue(overview["structure"][0]["source_locators"])
            confirmed = confirm_object_overview(pack, "骨架与来源定位已人工核对")
            self.assertEqual(confirmed["status"], "confirmed")
            metadata = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
            self.assertEqual(
                metadata["semantic_contract"]["overview_confirmation"],
                "confirmed",
            )
            self.assertEqual(
                [item for item in validate_pack(pack) if item.severity == "error"],
                [],
            )


if __name__ == "__main__":
    unittest.main()
