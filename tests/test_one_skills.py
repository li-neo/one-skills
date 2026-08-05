from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from one_skills.compiler import capability_from_candidate, compile_skill
from one_skills.database import KnowledgeDB
from one_skills.delivery import prepare_darwin
from one_skills.evaluation import aggregate_results, evaluate_pack, paired_decision
from one_skills.ingest import IngestionError, assert_public_host, ingest_file, structural_chunks
from one_skills.models import Candidate
from one_skills.pipeline import (
    PipelineError,
    advance_phase,
    create_pack,
    init_workspace,
    load_state,
)
from one_skills.retrieval import HybridRetriever, local_embedding
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


class CompilerEvaluationTests(unittest.TestCase):
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
