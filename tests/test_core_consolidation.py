from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from one_skills.core_assets import (
    ConcurrentPackUpdateError,
    load_pack_metadata,
    load_reproducibility,
    load_source_manifest,
    save_pack_metadata,
    save_reproducibility,
)
from one_skills.delivery import DeliveryError, install_pack
from one_skills.distillation_quality import assess_distillation_quality
from one_skills.ingest import IngestionError
from one_skills.lifecycle import load_state, save_state
from one_skills.migrations import migrate_pack, rollback_pack_migration
from one_skills.pipeline import create_pack, revoke_source
from one_skills.schema_runtime import validate_schema
from one_skills.utils import dump_json, load_json
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

    @staticmethod
    def _downgrade_pack(pack: Path, version: str) -> tuple[dict, dict]:
        metadata = load_pack_metadata(pack)
        lifecycle = metadata["lifecycle"]
        quality = load_source_manifest(pack)["quality"]
        metadata["schema_version"] = version
        metadata.pop("revision", None)
        metadata.pop("migration_history", None)
        metadata.pop("migrated_at", None)
        if version in {"0.2", "0.3"}:
            recipe_lock = metadata.pop("recipe_lock")
            reproducibility = metadata.pop("reproducibility")
            metadata.pop("lifecycle")
            dump_json(pack / "PIPELINE_STATE.json", lifecycle)
            dump_json(pack / "RECIPE_LOCK.json", recipe_lock)
            dump_json(pack / "PROTECTED_CONSTRAINTS.json", reproducibility)
            manifest = load_source_manifest(pack)
            manifest.pop("quality")
            dump_json(pack / "SOURCE_MANIFEST.json", manifest)
            dump_json(pack / "SOURCE_QUALITY.json", quality)
            (pack / "PIPELINE_STATE.md").write_text(
                "legacy projection\n",
                encoding="utf-8",
            )
            (pack / "OBJECT_MAP.md").write_text(
                "legacy projection\n",
                encoding="utf-8",
            )
        if version == "0.2":
            metadata.pop("semantic_contract", None)
            metadata.pop("object_overview_hash", None)
            metadata.pop("capability_portfolio_hash", None)
            metadata.pop("capability_graph_hash", None)
        dump_json(pack / "pack.json", metadata)
        return lifecycle, quality

    def test_new_pack_uses_consolidated_authoritative_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            metadata = load_pack_metadata(pack)
            self.assertEqual(metadata["schema_version"], "1.0")
            self.assertGreaterEqual(metadata["revision"], 1)
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

    def test_public_test_schema_accepts_critical_and_rejects_unknown_risk(self) -> None:
        cases = [
            {
                "id": "trigger",
                "type": "should_trigger",
                "prompt": "trigger",
                "expected": "run",
                "risk": "critical",
            },
            {
                "id": "negative",
                "type": "should_not_trigger",
                "prompt": "negative",
                "expected": "abstain",
                "risk": "low",
            },
            {
                "id": "edge",
                "type": "edge_case",
                "prompt": "edge",
                "expected": "fallback",
                "risk": "high",
            },
        ]
        self.assertEqual(
            validate_schema(cases, "test-prompts.schema.json"),
            [],
        )
        cases[0]["risk"] = "extreme"
        self.assertEqual(
            len(validate_schema(cases, "test-prompts.schema.json")),
            1,
        )

    def test_failed_creation_leaves_no_pack_and_can_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            source.write_text(
                "# Method\n\n先验证事实，再执行可逆操作。",
                encoding="utf-8",
            )
            workspace = root / "workspace"
            with patch(
                "one_skills.source_workflow._map_and_extract",
                side_effect=OSError("injected disk failure"),
            ), self.assertRaises(OSError):
                create_pack(
                    workspace,
                    [str(source)],
                    "methodology",
                    "quick",
                    "retryable-pack",
                    "public",
                )
            self.assertFalse((workspace / "packs" / "retryable-pack").exists())
            staging = workspace / ".one" / "staging" / "packs"
            self.assertEqual(list(staging.iterdir()), [])

            pack = create_pack(
                workspace,
                [str(source)],
                "methodology",
                "quick",
                "retryable-pack",
                "public",
            )
            self.assertEqual(
                pack,
                workspace.resolve() / "packs" / "retryable-pack",
            )
            self.assertTrue((pack / "SOURCE_MANIFEST.json").exists())

    def test_source_set_is_all_or_nothing_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            source.write_text("# Source\n\nvalid content", encoding="utf-8")
            workspace = root / "workspace"
            with self.assertRaises(IngestionError) as rejected:
                create_pack(
                    workspace,
                    [str(source), str(root / "missing.md")],
                    "content",
                    "quick",
                    "partial-pack",
                    "public",
                )
            self.assertIn("no sources were accepted", str(rejected.exception))
            self.assertFalse((workspace / "packs" / "partial-pack").exists())

    def test_pack_metadata_updates_are_locked_and_revision_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            before = load_pack_metadata(pack)["revision"]
            state = load_state(pack)
            state["phases"]["verify"]["notes"] = "concurrent lifecycle update"
            constraints = load_reproducibility(pack)
            constraints["concurrency_marker"] = "preserved"
            barrier = Barrier(2)

            def write_state() -> None:
                barrier.wait()
                save_state(pack, state)

            def write_constraints() -> None:
                barrier.wait()
                save_reproducibility(pack, constraints)

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(write_state),
                    executor.submit(write_constraints),
                ]
                for future in futures:
                    future.result()
            metadata = load_pack_metadata(pack)
            self.assertEqual(metadata["revision"], before + 2)
            self.assertEqual(
                metadata["lifecycle"]["phases"]["verify"]["notes"],
                "concurrent lifecycle update",
            )
            self.assertEqual(
                metadata["reproducibility"]["concurrency_marker"],
                "preserved",
            )

            stale = load_pack_metadata(pack)
            current = load_pack_metadata(pack)
            current["updated_at"] = "current"
            save_pack_metadata(pack, current)
            stale["updated_at"] = "stale"
            with self.assertRaises(ConcurrentPackUpdateError):
                save_pack_metadata(pack, stale)

    def test_revocation_intent_blocks_delivery_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = self._pack(root)
            manifest = load_source_manifest(pack)
            source_id = manifest["sources"][0]["source_id"]
            workspace = root / "workspace"
            with patch(
                "one_skills.source_workflow._invalidate_revoked_evidence",
                side_effect=OSError("injected Pack update failure"),
            ), self.assertRaises(OSError):
                revoke_source(workspace, source_id, "authorization withdrawn")

            intents = list(
                (workspace / ".one" / "revocations").glob("*.json")
            )
            self.assertEqual(len(intents), 1)
            self.assertEqual(load_pack_metadata(pack)["schema_version"], "1.0")
            self.assertEqual(load_json(intents[0])["status"], "pending")
            with self.assertRaisesRegex(
                DeliveryError,
                "pending source revocation",
            ):
                install_pack(pack, root / "installed")

            event = revoke_source(
                workspace,
                source_id,
                "authorization withdrawn",
            )
            self.assertEqual(event["affected_packs"], [pack.name])
            self.assertEqual(load_json(intents[0])["status"], "completed")

    def test_pack_migration_matrix_is_idempotent(self) -> None:
        for version in ("0.2", "0.3", "0.4"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temporary:
                pack = self._pack(Path(temporary))
                lifecycle, quality = self._downgrade_pack(pack, version)

                report = migrate_pack(pack)
                self.assertEqual(report["schema_version"], "1.0")
                self.assertEqual(
                    len(report["removed_legacy_assets"]),
                    6 if version in {"0.2", "0.3"} else 0,
                )
                migrated = load_pack_metadata(pack)
                self.assertEqual(migrated["lifecycle"], lifecycle)
                self.assertEqual(load_source_manifest(pack)["quality"], quality)
                self.assertEqual(
                    migrated["migration_history"][-1]["from"],
                    version,
                )
                self.assertEqual(migrate_pack(pack)["status"], "unchanged")
                self.assertFalse(
                    [
                        item
                        for item in validate_pack(pack)
                        if item.severity == "error"
                    ]
                )

    def test_interrupted_migration_resumes_and_can_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = self._pack(Path(temporary))
            self._downgrade_pack(pack, "0.3")
            calls = 0

            def fail_once(path: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected migration cleanup failure")
                path.unlink()

            with patch(
                "one_skills.migrations._remove_legacy_asset",
                side_effect=fail_once,
            ), self.assertRaises(OSError):
                migrate_pack(pack)
            journal = (
                pack
                / "audit"
                / "migrations"
                / "pack-schema-1.0"
                / "journal.json"
            )
            self.assertEqual(load_json(journal)["status"], "pending")

            report = migrate_pack(pack)
            self.assertEqual(report["schema_version"], "1.0")
            self.assertEqual(load_json(journal)["status"], "completed")
            rolled_back = rollback_pack_migration(pack)
            self.assertEqual(rolled_back["schema_version"], "0.3")
            self.assertEqual(load_pack_metadata(pack)["schema_version"], "0.3")
            self.assertTrue((pack / "PIPELINE_STATE.json").exists())

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
