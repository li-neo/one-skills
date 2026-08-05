from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from one_skills.compiler import capability_from_candidate, compile_skill
from one_skills.database import KnowledgeDB
from one_skills.delivery import export_pack, install_pack, prepare_darwin, release_pack
from one_skills.evaluation import aggregate_results, evaluate_pack, paired_decision
from one_skills.ingest import IngestionError, assert_public_host, ingest_file, structural_chunks
from one_skills.models import Candidate
from one_skills.pipeline import (
    PipelineError,
    advance_phase,
    create_pack,
    init_workspace,
    load_state,
    update_pack,
    verify_and_compile_with_model,
)
from one_skills.retrieval import HybridRetriever, local_embedding
from one_skills.recipes import promotion_decision
from one_skills.validation import validate_skill


class IngestionTests(unittest.TestCase):
    def test_private_network_is_rejected(self) -> None:
        with self.assertRaises(IngestionError):
            assert_public_host("127.0.0.1")

    def test_file_ingestion_and_structural_chunking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.md"
            source.write_text("# First\n\n" + "Evidence sentence. " * 80 + "\n\n# Second\n\nDone.", encoding="utf-8")
            document = ingest_file(source)
            chunks = structural_chunks(document, "document-1", 1, target_characters=300)
            self.assertGreaterEqual(len(chunks), 2)
            self.assertEqual(chunks[0].document_id, "document-1")


class DatabaseAndRetrievalTests(unittest.TestCase):
    def test_acl_hybrid_search_and_person_fact_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            source.write_text("# Decisions\n\n先确认瓶颈，再比较每单位瓶颈的价值。", encoding="utf-8")
            document = ingest_file(source, "authorized")
            with KnowledgeDB(root / "knowledge.db") as database:
                _, document_id, version, _ = database.add_document(document, "methodology")
                chunks = structural_chunks(document, document_id, version)
                database.add_chunks(chunks, {item.id: local_embedding(item.text) for item in chunks})
                retriever = HybridRetriever(database)
                self.assertEqual(retriever.search("瓶颈价值", {"public"}), [])
                results = retriever.search("瓶颈价值", {"authorized"})
                self.assertTrue(results)
                source.write_text("# Decisions\n\n新版本要求先验证约束，再分配资源。", encoding="utf-8")
                updated = ingest_file(source, "authorized")
                _, same_document_id, second_version, created = database.add_document(
                    updated, "methodology"
                )
                self.assertTrue(created)
                self.assertEqual(same_document_id, document_id)
                self.assertEqual(second_version, 2)
                updated_chunks = structural_chunks(updated, document_id, second_version)
                database.add_chunks(
                    updated_chunks,
                    {item.id: local_embedding(item.text) for item in updated_chunks},
                )
                self.assertEqual(retriever.search("单位瓶颈价值", {"authorized"}), [])
                self.assertTrue(retriever.search("验证约束", {"authorized"}))

                subject = database.add_person_subject("Example", "self")
                first = database.mutate_person_fact(
                    "ADD", subject, "preference", "偏好简洁输出", 0.9, "private-local"
                )
                second = database.mutate_person_fact(
                    "UPDATE",
                    subject,
                    "preference",
                    "偏好简洁且包含证据的输出",
                    0.95,
                    "private-local",
                    supersedes=first,
                )
                database.mutate_person_fact(
                    "REVOKE",
                    subject,
                    "preference",
                    "",
                    1.0,
                    "private-local",
                    supersedes=second,
                )
                statuses = {
                    row["id"]: row["status"]
                    for row in database.rows("SELECT id, status FROM person_facts")
                }
                self.assertEqual(statuses[first], "superseded")
                self.assertEqual(statuses[second], "revoked")


class PipelineTests(unittest.TestCase):
    def test_pipeline_blocks_at_independent_verification_and_cannot_skip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            source = root / "method.md"
            source.write_text(
                "# Context A\n\n原则是必须先识别瓶颈，再比较方案。\n\n"
                "# Context B\n\n案例中应该先识别瓶颈，然后才分配资源。\n",
                encoding="utf-8",
            )
            pack = create_pack(root, [str(source)], "methodology", "standard", "bottleneck")
            state = load_state(pack)
            self.assertEqual(state["current_phase"], "verify")
            self.assertEqual(state["phases"]["verify"]["status"], "blocked")
            with self.assertRaises(PipelineError):
                advance_phase(pack, "ship", "completed")
            self.assertTrue((pack / "candidates" / "candidates.json").exists())
            self.assertTrue((pack / "EVIDENCE_LEDGER.jsonl").exists())
            source.write_text(
                "# Context C\n\n新版本要求必须验证完成标准，并记录回滚路径。\n",
                encoding="utf-8",
            )
            impact = update_pack(pack, [str(source)])
            self.assertEqual(impact["new_source_versions"], 1)
            manifest = json.loads((pack / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
            versions = [
                item["document_version"]
                for item in manifest["sources"]
                if item["document_id"] == manifest["sources"][-1]["document_id"]
            ]
            self.assertEqual(versions, [1, 2])
            self.assertTrue((pack / "reports" / "IMPACT.md").exists())

    def test_independent_model_verification_compiles_profile_skill(self) -> None:
        class FakeProvider:
            def complete_json(self, system: str, user: str, schema_name: str) -> dict:
                del system, user
                if schema_name == "candidate-verification":
                    return {
                        "cross_domain": True,
                        "predictive": True,
                        "distinctive": True,
                        "actionable": True,
                        "boundary": True,
                        "novel_question": "如何处理一个来源未直接回答的新场景？",
                        "derived_answer": "先识别瓶颈，再比较单位瓶颈价值。",
                        "reason": "两个独立上下文支持同一机制。",
                    }
                return {
                    "name": "verified-bottleneck",
                    "problem": "在资源稀缺时排序方案",
                    "trigger": "当多个方案竞争同一稀缺资源时",
                    "inputs": ["候选方案", "稀缺资源", "价值证据"],
                    "procedure": ["确认瓶颈", "计算单位瓶颈价值", "排序并定义停止条件"],
                    "output": "带假设的优先级列表",
                    "done": "排序可由证据复核",
                    "boundaries": ["瓶颈未知时不排序"],
                    "failures": ["价值不可比"],
                    "fallback": "先做最小测量",
                }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "method.md"
            source.write_text(
                "# A\n\n必须先识别资源瓶颈，再比较单位瓶颈价值，这是决策方法。\n\n"
                "# B\n\n另一个案例也应该先识别资源瓶颈，然后再排序项目优先级。\n",
                encoding="utf-8",
            )
            pack = create_pack(
                root,
                [str(source)],
                "methodology",
                "standard",
                "model-case",
                "public",
            )
            values = json.loads((pack / "verified" / "decisions.json").read_text(encoding="utf-8"))
            self.assertTrue(values)
            values = [values[0]]
            (pack / "verified" / "decisions.json").write_text(
                json.dumps(values, ensure_ascii=False),
                encoding="utf-8",
            )
            skills = verify_and_compile_with_model(pack, FakeProvider())
            self.assertEqual(len(skills), 1)
            self.assertTrue((skills[0] / "SKILL.md").exists())
            self.assertEqual(load_state(pack)["current_phase"], "test")
            self.assertTrue((pack / "audit" / "model-verification.json").exists())
            tests = json.loads((skills[0] / "test-prompts.json").read_text(encoding="utf-8"))
            results = root / "agent-results.json"
            results.write_text(
                json.dumps([{"id": item["id"], "passed": True} for item in tests]),
                encoding="utf-8",
            )
            evaluate_pack(pack, results)
            release = release_pack(pack)
            self.assertEqual(release["status"], "released")
            self.assertEqual(load_state(pack)["current_phase"], "evolve")
            installed = install_pack(pack, root / "installed")
            self.assertTrue(Path(installed[0]["destination"]).joinpath("SKILL.md").exists())
            archive = export_pack(pack, root / "dist")
            self.assertGreater(archive.stat().st_size, 0)
            self.assertEqual(prepare_darwin(pack)["status"], "prepared")

    def test_model_verification_rejects_non_public_pack_without_authorization(self) -> None:
        class UnusedProvider:
            def complete_json(self, system: str, user: str, schema_name: str) -> dict:
                raise AssertionError("provider must not receive private data")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "private.md"
            source.write_text("必须保留这条私人方法和证据，不能外发。" * 10, encoding="utf-8")
            with self.assertRaises(PipelineError):
                create_pack(root, [str(source)], "person", "quick", "missing-consent")
            pack = create_pack(
                root,
                [str(source)],
                "person",
                "quick",
                "private-person",
                "private-local",
                "self",
            )
            with self.assertRaises(PipelineError):
                verify_and_compile_with_model(pack, UnusedProvider())


class CompilerEvaluationTests(unittest.TestCase):
    def test_recipe_promotion_uses_non_compensating_gates(self) -> None:
        baseline = {
            "task_success": 0.7,
            "false_trigger_rate": 0.1,
            "evidence_coverage": 0.8,
            "citation_accuracy": 0.9,
            "safety_rate": 1.0,
            "cost": 1.0,
            "latency": 10.0,
        }
        candidate = {**baseline, "task_success": 0.8, "safety_rate": 0.99}
        decision = promotion_decision(candidate= candidate, baseline=baseline, budgets={"cost": 2.0, "latency": 20.0})
        self.assertFalse(decision["promote"])
        candidate["safety_rate"] = 1.0
        self.assertTrue(
            promotion_decision(baseline, candidate, {"cost": 2.0, "latency": 20.0})["promote"]
        )

    def test_all_profiles_have_distinct_compilation_contracts(self) -> None:
        candidate = Candidate(
            title="profile-contract",
            candidate_type="framework",
            summary="一个经过验证、能够执行并具有清晰边界的机制。",
            evidence_ids=["ev-1"],
            source_contexts=["A", "B"],
            cross_domain=True,
            predictive=True,
            distinctive=True,
            actionable=True,
            status="accepted",
        )
        outputs = {}
        for profile in ("person", "content", "methodology", "sop", "tool", "skill", "hybrid"):
            capability = capability_from_candidate(candidate, profile)
            outputs[profile] = (tuple(capability.procedure), tuple(capability.boundaries))
        self.assertEqual(len(set(outputs.values())), 7)

    def _skill(self, root: Path) -> tuple[Path, list[dict[str, object]]]:
        candidate = Candidate(
            title="decision-bottleneck",
            candidate_type="framework",
            summary="先识别当前稀缺资源，再比较每单位瓶颈产生的可验证价值。",
            evidence_ids=["ev-1"],
            source_contexts=["A", "B"],
            cross_domain=True,
            predictive=True,
            distinctive=True,
            actionable=True,
            status="accepted",
        )
        capability = capability_from_candidate(candidate)
        evidence = [{"id": "ev-1", "claim": candidate.summary, "locator": "source.md#L2"}]
        skill = compile_skill(root, capability, evidence)
        tests = json.loads((skill / "test-prompts.json").read_text(encoding="utf-8"))
        return skill, tests

    def test_compile_validate_evaluate_and_darwin_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            (pack / "skills").mkdir()
            skill, tests = self._skill(pack)
            self.assertFalse([item for item in validate_skill(skill) if item.severity == "error"])
            results = pack / "agent-results.json"
            results.write_text(
                json.dumps([{"id": item["id"], "passed": True} for item in tests]),
                encoding="utf-8",
            )
            report = evaluate_pack(pack, results)
            self.assertEqual(report["skills"][0]["agent_results"]["rate"], 1.0)
            request = prepare_darwin(pack)
            self.assertEqual(request["status"], "prepared")
            self.assertTrue((pack / "evolution" / "DARWIN_REQUEST.md").exists())

    def test_result_filtering_and_paired_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.json"
            path.write_text(
                json.dumps([
                    {"id": "local", "passed": True},
                    {"id": "other", "passed": False},
                ]),
                encoding="utf-8",
            )
            result, warnings = aggregate_results(path, {"local"})
            self.assertEqual(result["rate"], 1.0)
            self.assertEqual(warnings, [])
        self.assertEqual(
            paired_decision([
                {"verdict": "after"},
                {"verdict": "tie"},
                {"verdict": "after"},
            ])["decision"],
            "keep",
        )


if __name__ == "__main__":
    unittest.main()
