from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from one_skills.compiler import (
    capability_from_candidate,
    compile_skill,
    export_profile_templates,
)
from one_skills.constants import MAX_LOCAL_BYTES
from one_skills.core_assets import (
    load_pack_metadata,
    load_reproducibility,
    save_pack_metadata,
    save_reproducibility,
)
from one_skills.delivery import (
    DeliveryError,
    export_pack,
    install_pack,
    prepare_darwin,
    release_pack,
)
from one_skills.evaluation import aggregate_results, evaluate_pack, paired_decision
from one_skills.experience import mine_experience_candidates, record_experience
from one_skills.extraction import (
    extract_candidates_with_model,
    extract_structured_claims,
    verify_candidates,
)
from one_skills.guided import (
    GuidedSessionError,
    advance_session,
    confirm_checkpoint,
    create_pack_from_session,
    init_session,
    load_session,
    record_event,
    update_session_profile,
    validate_guided_workspace,
)
from one_skills.ingest import (
    IngestionError,
    _assert_archive_budget,
    _line_locator,
    assert_public_host,
    ingest_file,
    structural_chunks,
)
from one_skills.learning import init_learner, next_learning_node, record_attempt
from one_skills.models import Candidate, Chunk
from one_skills.pipeline import (
    PipelineError,
    advance_phase,
    create_pack,
    init_workspace,
    lineage,
    load_state,
    revoke_source,
    update_pack,
    verify_and_compile_with_model,
)
from one_skills.provider import ProviderError
from one_skills.recipes import promotion_decision
from one_skills.retrieval import HybridRetriever
from one_skills.routing import route_intent
from one_skills.skill_retrieval import search_skills
from one_skills.source_quality import audit_source_catalog
from one_skills.storage import LocalBlobStore
from one_skills.validation import validate_pack, validate_skill


class IngestionTests(unittest.TestCase):
    def test_local_blob_store_reads_platform_file_uri(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source with space.md"
            path.write_text("content", encoding="utf-8")
            store = LocalBlobStore(Path(temporary) / "blobs")
            self.assertTrue(store.exists(path.resolve().as_uri()))

    def test_line_locator_merges_existing_fragment(self) -> None:
        self.assertEqual(
            _line_locator("https://example.org/book#chapter", 42),
            "https://example.org/book#chapter",
        )
        self.assertEqual(
            _line_locator("https://example.org/book", 42),
            "https://example.org/book",
        )
        self.assertEqual(_line_locator("/tmp/book.md", 42), "/tmp/book.md#L42")

    def test_source_catalog_gates_quality_and_materializes_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            captured = root / "captured"
            captured.mkdir()
            for name in ("primary", "critical", "anchor", "holdout"):
                (captured / f"{name}.md").write_text(
                    f"# {name}\n\n必须先调查事实，再说明边界和反例。" * 6,
                    encoding="utf-8",
                )
            catalog = {
                "schema_version": "1.0",
                "subject": "Historical method",
                "research_questions": ["method", "failure"],
                "requirements": {
                    "minimum_independent_groups": 3,
                    "minimum_primary_sources": 1,
                    "required_roles": [
                        "evidence",
                        "counterevidence",
                        "verification_anchor",
                    ],
                    "minimum_coverage": 1.0,
                },
                "sources": [
                    {
                        "id": "primary",
                        "ingest": "captured/primary.md",
                        "uri": "https://example.org/primary",
                        "title": "Primary",
                        "creator": "Author",
                        "authority": "primary",
                        "directness": "direct",
                        "independence_group": "author",
                        "role": "evidence",
                        "coverage": ["method"],
                        "temporal_scope": "historical",
                        "locator": "section 1",
                        "usage_rights": "link-and-short-quotes",
                        "access": "public",
                    },
                    {
                        "id": "critical",
                        "ingest": "captured/critical.md",
                        "uri": "https://example.edu/critical",
                        "title": "Critical history",
                        "creator": "University",
                        "authority": "scholarly",
                        "directness": "derived",
                        "independence_group": "university",
                        "role": "counterevidence",
                        "coverage": ["failure"],
                        "temporal_scope": "historical",
                        "locator": "chapter 2",
                        "usage_rights": "link-and-short-quotes",
                        "access": "public",
                    },
                    {
                        "id": "anchor",
                        "ingest": "captured/anchor.md",
                        "uri": "https://archive.example/anchor",
                        "title": "Independent archive",
                        "creator": "Archive",
                        "authority": "official",
                        "directness": "direct",
                        "independence_group": "archive",
                        "role": "verification_anchor",
                        "coverage": ["method", "failure"],
                        "temporal_scope": "historical",
                        "locator": "record 3",
                        "usage_rights": "link-and-short-quotes",
                        "access": "public",
                    },
                    {
                        "id": "holdout",
                        "ingest": "captured/holdout.md",
                        "uri": "https://holdout.example/eval",
                        "title": "Holdout",
                        "creator": "Evaluator",
                        "authority": "scholarly",
                        "directness": "derived",
                        "independence_group": "holdout",
                        "role": "evaluation_only",
                        "coverage": ["method"],
                        "temporal_scope": "historical",
                        "locator": "case 1",
                        "usage_rights": "link-and-short-quotes",
                        "access": "public",
                    },
                ],
            }
            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps(catalog, ensure_ascii=False),
                encoding="utf-8",
            )
            report = audit_source_catalog(catalog_path, "content", "deep")
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["metrics"]["selected_count"], 3)
            pack = create_pack(
                root / "workspace",
                [],
                "content",
                "deep",
                "historical-method",
                "public",
                None,
                catalog_path,
            )
            manifest = json.loads(
                (pack / "SOURCE_MANIFEST.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                {item["authority"] for item in manifest["sources"]},
                {"primary", "scholarly", "official"},
            )
            self.assertTrue((pack / "LEARNING_PATH.json").exists())
            self.assertEqual(
                [item for item in validate_pack(pack) if item.severity == "error"],
                [],
            )
            self.assertEqual(
                len([item for item in manifest["sources"] if item["active"]]),
                3,
            )

    def test_hybrid_candidate_requires_independent_provenance_groups(self) -> None:
        candidate = Candidate(
            title="recurring-method",
            candidate_type="framework",
            summary="必须先调查两个独立场景，再根据反证与执行结果持续修正当前判断。",
            evidence_ids=["a", "b"],
            source_contexts=["same-source::A", "same-source::B"],
            source_ids=["same-source"],
            independence_groups=["same-publisher"],
        )
        verified = verify_candidates(
            [candidate],
            deep=True,
            require_independent_sources=True,
        )[0]
        self.assertTrue(verified.cross_domain)
        self.assertTrue(verified.distinctive)
        self.assertFalse(verified.source_independent)
        self.assertEqual(verified.status, "rejected")

    def test_structured_claim_keys_join_independent_sources(self) -> None:
        statement = "必须把一线证据、暂时判断、可逆试验和独立坏消息通道组成闭环。"
        chunks = [
            Chunk(
                id=f"chunk-{index}",
                document_id=f"document-{index}",
                document_version=1,
                section_path="Structured claim",
                ordinal=0,
                text=(
                    "Claim-Key: feedback-integrity\n"
                    f"Claim-Statement: {statement}\n"
                    "Claim-Type: framework\n"
                    f"Evidence: 独立来源{index}提供了可定位的支持证据。"
                ),
                content_hash=str(index) * 64,
                access_level="public",
                source_locator=f"source-{index}#L1",
                source_key=f"source-{index}",
                independence_group=f"group-{index}",
                authority="primary" if index == 1 else "scholarly",
            )
            for index in (1, 2)
        ]
        candidates, evidence = extract_structured_claims(chunks, "methodology")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(evidence), 2)
        verified = verify_candidates(candidates, deep=True)[0]
        self.assertTrue(verified.cross_domain)
        self.assertTrue(verified.source_independent)
        self.assertTrue(verified.distinctive)
        self.assertEqual(verified.status, "needs_model_verification")

    def test_archive_expansion_budget_is_enforced(self) -> None:
        class Entry:
            file_size = MAX_LOCAL_BYTES + 1

        class Archive:
            def infolist(self) -> list:
                return [Entry()]

        with self.assertRaises(IngestionError):
            _assert_archive_budget(Archive(), Path("oversized.epub"))

    def test_semantic_extractor_rejects_non_verbatim_evidence(self) -> None:
        class BadProvider:
            def complete_json(self, system: str, user: str, schema_name: str) -> dict:
                del system, schema_name
                payload = json.loads(user)
                return {
                    "candidates": [
                        {
                            "title": "invented",
                            "summary": "invented",
                            "tags": [],
                            "evidence": [
                                {
                                    "chunk_id": payload["chunks"][0]["id"],
                                    "quote": "这句话不在原文中",
                                }
                            ],
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.md"
            source.write_text("# Source\n\n真实证据只存在于这里。" * 5, encoding="utf-8")
            document = ingest_file(source, "public")
            chunks = structural_chunks(document, "document-1", 1)
            with self.assertRaises(ProviderError):
                extract_candidates_with_model(BadProvider(), chunks, "content")

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
    def test_field_aware_skill_retrieval_and_official_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            investigation = root / "investigation-first"
            contradiction = root / "contradiction-analysis"
            investigation.mkdir()
            contradiction.mkdir()
            (investigation / "SKILL.md").write_text(
                "---\n"
                "name: investigation-first\n"
                "description: |\n"
                "  Collects first-hand evidence before high-impact decisions. "
                "Use when reports conflict or no one has interviewed users.\n"
                "license: MIT\n"
                "compatibility: Requires access to source documents.\n"
                "metadata:\n"
                "  author: example-org\n"
                "  version: \"1.0\"\n"
                "allowed-tools: Read WebSearch\n"
                "---\n"
                "# Investigation\n\n"
                "## 触发场景\n用户只看二手报告、尚未访谈一线用户。\n\n"
                "## 工作流\n先定义问题，再访谈不同角色，最后记录反证。\n\n"
                "## 边界\n已有充分一手证据时不要重复调查。\n",
                encoding="utf-8",
            )
            (contradiction / "SKILL.md").write_text(
                "---\n"
                "name: contradiction-analysis\n"
                "description: Maps competing objectives and selects a bottleneck. "
                "Use when many conflicts compete for attention.\n"
                "---\n"
                "# Contradiction\n\n"
                "## 触发场景\n多个目标和资源矛盾纠缠。\n\n"
                "## 工作流\n列出矛盾并选择牵动全局的一项。\n\n"
                "## 边界\n事实信息不足时先调查。\n",
                encoding="utf-8",
            )
            findings = validate_skill(investigation)
            self.assertNotIn(
                "frontmatter.keys",
                {item.code for item in findings if item.severity == "error"},
            )
            result = search_skills(
                "团队只看了行业报告，没有访谈一线用户，先怎么调查？",
                [root],
            )
            self.assertEqual(result["status"], "selected")
            self.assertEqual(result["results"][0]["name"], "investigation-first")
            self.assertIn("triggers", result["results"][0]["field_scores"])

            explicit = root / "explicit-only"
            explicit.mkdir()
            (explicit / "SKILL.md").write_text(
                "---\n"
                "name: explicit-only\n"
                "description: Handles confidential review methods. "
                "Use only when explicitly invoked.\n"
                "metadata:\n"
                "  one-skills.activation: explicit\n"
                "  one-skills.aliases: run-explicit,显式审查\n"
                "---\n"
                "# Explicit\n\n"
                "## 触发场景\n仅在明确点名时运行审查。\n\n"
                "## 工作流\n读取证据并输出审查结果。\n\n"
                "## 边界\n普通审查问题不自动运行。\n",
                encoding="utf-8",
            )
            self.assertEqual(
                search_skills("请审查这份材料", [explicit])["status"],
                "abstain",
            )
            selected = search_skills("run-explicit 审查这份材料", [explicit])
            self.assertEqual(selected["status"], "selected")
            self.assertTrue(selected["results"][0]["activation_eligible"])

    def test_flat_file_hybrid_search_filters_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            source = root / "source.md"
            source.write_text(
                "# Decisions\n\n先确认瓶颈，再比较每单位瓶颈的价值。",
                encoding="utf-8",
            )
            create_pack(
                root,
                [str(source)],
                "methodology",
                "quick",
                "bottleneck",
                "authorized",
            )
            retriever = HybridRetriever(root)
            self.assertEqual(retriever.search("瓶颈价值", {"public"}), [])
            results = retriever.search("瓶颈价值", {"authorized"})
            self.assertTrue(results)
            self.assertEqual(results[0]["pack"], "bottleneck")

    def test_graph_neighbors_follow_capability_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            source_a = root / "source-a.md"
            source_a.write_text(
                "# Input\n\nidentify the governing constraint",
                encoding="utf-8",
            )
            source_b = root / "source-b.md"
            source_b.write_text(
                "# Related\n\nverify the rollback checkpoint",
                encoding="utf-8",
            )
            pack = create_pack(
                root,
                [str(source_a), str(source_b)],
                "methodology",
                "quick",
                "shared",
                "authorized",
            )
            chunks = json.loads(
                (pack / "sources" / "chunks.json").read_text(encoding="utf-8")
            )
            chunk_a = next(
                chunk for chunk in chunks if "governing constraint" in chunk["text"]
            )
            chunk_b = next(
                chunk for chunk in chunks if "rollback checkpoint" in chunk["text"]
            )
            with (pack / "EVIDENCE_LEDGER.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                for chunk, claim in (
                    (chunk_a, "claim-input"),
                    (chunk_b, "claim-related"),
                ):
                    handle.write(
                        json.dumps(
                            {
                                "id": claim,
                                "claim": "claim",
                                "evidence_type": "quote",
                                "source": chunk["document_id"],
                                "locator": chunk["source_locator"],
                                "confidence": 0.9,
                                "inference_level": "none",
                                "permission": "authorized",
                                "chunk_id": chunk["id"],
                                "document_version": chunk["document_version"],
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            skill_dir = pack / "skills" / "shared-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "capability.json").write_text(
                json.dumps(
                    {
                        "id": "capability-shared",
                        "name": "shared",
                        "problem": "p",
                        "trigger": "t",
                        "inputs": [],
                        "procedure": ["step"],
                        "output": "o",
                        "done": "d",
                        "boundaries": [],
                        "failures": [],
                        "fallback": "f",
                        "evidence_ids": ["claim-input", "claim-related"],
                        "confidence": 0.9,
                        "relations": [],
                        "module_type": "entry",
                        "status": "verified",
                    },
                    ensure_ascii=False,
                )
            )
            retriever = HybridRetriever(root)
            self.assertEqual(
                retriever.graph_neighbors([chunk_a["id"]], {"authorized"}),
                [chunk_b["id"]],
            )


class PipelineTests(unittest.TestCase):
    def test_learning_state_and_experience_candidates_are_evidence_gated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "course.md"
            source.write_text(
                "# Foundation\n\n先理解输入和输出。\n\n"
                "# Practice\n\n再用新问题检查是否掌握。",
                encoding="utf-8",
            )
            pack = create_pack(
                root / "workspace",
                [str(source)],
                "content",
                "quick",
                "course",
                "public",
            )
            init_learner(pack, "alice")
            first = next_learning_node(pack, "alice")
            self.assertIsNotNone(first)
            record_attempt(pack, "alice", first["id"], 0.9, "能够解释并举例")
            second = next_learning_node(pack, "alice")
            self.assertIsNotNone(second)
            self.assertNotEqual(first["id"], second["id"])

            record_experience(
                pack,
                "course-skill",
                "用户把相关性当成因果性",
                "corrected",
                "回答缺少因果边界",
                "run:1",
                "先列替代解释，再寻找干预证据。",
                "public",
            )
            self.assertEqual(
                mine_experience_candidates(pack)["candidate_count"],
                0,
            )
            record_experience(
                pack,
                "course-skill",
                "用户把相关性当成因果性",
                "failure",
                "再次遗漏替代解释",
                "run:2",
                access="public",
            )
            record_experience(
                pack,
                "course-skill",
                "用户把相关性当成因果性",
                "failure",
                "holdout failure",
                "eval:1",
                access="public",
                scope="evaluation",
            )
            report = mine_experience_candidates(pack)
            self.assertEqual(report["candidate_count"], 1)
            self.assertEqual(len(report["evaluation_event_ids"]), 1)
            self.assertNotIn(
                report["evaluation_event_ids"][0],
                report["candidates"][0]["supporting_event_ids"],
            )

    def test_router_abstains_on_ambiguous_intent(self) -> None:
        routed = route_intent("帮我整理一下这个东西")
        self.assertTrue(routed["needs_confirmation"])
        # "人物" no longer has a dedicated person Profile; the intent abstains.
        unclear = route_intent("把毛泽东的思维方法蒸馏成人物 skill")
        self.assertTrue(unclear["needs_confirmation"])

    def test_guided_session_preserves_evidence_class_in_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guided = root / "guided"
            state = init_session(
                guided,
                "Decision Method",
                "methodology",
                target_capability="review a proposal",
                target_user="product team",
                output_goal="reviewer Skill",
                access_level="authorized",
            )
            self.assertEqual(state["recommended_profile"], "methodology")
            self.assertLessEqual(len(state["next_questions"]), 3)
            self.assertEqual(advance_session(guided)["current_stage"], "scope")
            confirm_checkpoint(guided, "scope", "confirmed", "scope accepted")
            self.assertEqual(
                advance_session(guided)["current_stage"], "evidence_inventory"
            )
            confirm_checkpoint(
                guided,
                "evidence_inventory",
                "confirmed",
                "conversation authorized",
            )
            self.assertEqual(advance_session(guided)["current_stage"], "interview")
            event = record_event(
                guided,
                {
                    "kind": "answer",
                    "content": "我会先确认方案承载的决定，再检查不可逆风险。",
                    "evidence_class": "self_report",
                    "permission": "authorized",
                    "locator": "conversation:turn-1",
                },
            )
            source_event = record_event(
                guided,
                {
                    "kind": "source",
                    "content": "A source is available separately.",
                    "evidence_class": "unknown",
                    "permission": "authorized",
                    "locator": "source-inventory:item-1",
                },
            )
            pack, materialized = create_pack_from_session(
                guided, root / "workspace", "quick"
            )
            self.assertEqual(materialized, 1)
            self.assertEqual(load_session(guided)["pack_path"], str(pack))
            ledger = [
                json.loads(line)
                for line in (pack / "EVIDENCE_LEDGER.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line
            ]
            preserved = next(item for item in ledger if item["id"] == event["id"])
            self.assertEqual(preserved["evidence_type"], "self_report")
            self.assertEqual(preserved["permission"], "authorized")
            self.assertNotIn(source_event["id"], {item["id"] for item in ledger})
            self.assertEqual(validate_guided_workspace(guided), [])
            self.assertEqual(
                [item for item in validate_pack(pack) if item.severity == "error"],
                [],
            )

    def test_guided_session_enforces_consent_and_evidence_grade(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(GuidedSessionError):
                init_session(root / "unsupported-object", "Private Person", "person")
            with self.assertRaises(GuidedSessionError):
                init_session(
                    root / "bad-public-only",
                    "Public Method",
                    "methodology",
                    consent="public-only",
                    access_level="private-local",
                )
            guided = root / "method"
            init_session(
                guided,
                "Method",
                "methodology",
                target_capability="review",
                consent="self",
            )
            with self.assertRaises(GuidedSessionError):
                record_event(
                    guided,
                    {
                        "kind": "answer",
                        "content": "I always identify risk first.",
                        "evidence_class": "observed_behavior",
                        "permission": "private-local",
                        "locator": "conversation:turn-1",
                    },
                )
            self.assertEqual(load_session(guided)["evidence_counts"]["observed_behavior"], 0)

    def test_guided_session_requires_stage_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            guided = Path(temporary) / "guided"
            init_session(guided, "Method", "methodology")
            with self.assertRaises(GuidedSessionError):
                advance_session(guided)
            update_session_profile(guided, target_capability="triage incidents")
            advance_session(guided)
            with self.assertRaises(GuidedSessionError):
                advance_session(guided)
            with self.assertRaises(GuidedSessionError):
                confirm_checkpoint(guided, "ship", "confirmed")

    def test_unregistered_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "controls.md"
            source.write_text(
                "必须记录控制证据，并在例外发生时停止发布。" * 8,
                encoding="utf-8",
            )
            with self.assertRaises(PipelineError):
                create_pack(
                    root,
                    [str(source)],
                    "compliance",
                    "quick",
                    "control-pack",
                )

    def test_pipeline_blocks_at_independent_verification_and_cannot_skip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            source = root / "method.md"
            source.write_text(
                "# Context A\n\n原则是必须先识别真实资源瓶颈，再比较每个候选方案的单位价值与风险。\n\n"
                "# Context B\n\n案例中应该先识别制约结果的瓶颈，然后才按证据分配有限资源。\n",
                encoding="utf-8",
            )
            pack = create_pack(root, [str(source)], "methodology", "standard", "bottleneck")
            state = load_state(pack)
            self.assertEqual(state["current_phase"], "verify")
            self.assertEqual(state["phases"]["verify"]["status"], "blocked")
            metadata = load_pack_metadata(pack)
            recipe_lock = metadata["recipe_lock"]
            self.assertEqual(recipe_lock["recipe"]["profile"], "methodology")
            constraints = load_reproducibility(pack)
            self.assertEqual(len(constraints["source_hashes"]), 1)
            recipe_lock["recipe"]["profile"] = "content"
            metadata["recipe_lock"] = recipe_lock
            save_pack_metadata(pack, metadata)
            self.assertIn(
                "recipe.profile_mismatch",
                {
                    item.code
                    for item in validate_pack(pack)
                    if item.severity == "error"
                },
            )
            recipe_lock["recipe"]["profile"] = "methodology"
            metadata["recipe_lock"] = recipe_lock
            save_pack_metadata(pack, metadata)
            source_key = next(iter(constraints["source_hashes"]))
            source_hash = constraints["source_hashes"][source_key]
            constraints["source_hashes"][source_key] = "0" * 64
            save_reproducibility(pack, constraints)
            self.assertIn(
                "source.hash_drift",
                {
                    item.code
                    for item in validate_pack(pack)
                    if item.severity == "error"
                },
            )
            constraints["source_hashes"][source_key] = source_hash
            save_reproducibility(pack, constraints)
            with self.assertRaises(PipelineError):
                advance_phase(pack, "ship", "completed")
            self.assertTrue((pack / "candidates" / "candidates.json").exists())
            self.assertTrue((pack / "EVIDENCE_LEDGER.jsonl").exists())
            old_quote_ids = {
                json.loads(line)["id"]
                for line in (pack / "EVIDENCE_LEDGER.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            }
            initial_manifest = json.loads(
                (pack / "SOURCE_MANIFEST.json").read_text(encoding="utf-8")
            )
            self.assertTrue(initial_manifest["sources"][0]["raw_uri"].startswith("file:"))
            old_source = initial_manifest["sources"][0]
            verified_position_id = "ev-old-verified-position"
            with (pack / "EVIDENCE_LEDGER.jsonl").open(
                "a",
                encoding="utf-8",
            ) as ledger:
                ledger.write(
                    json.dumps(
                        {
                            "id": verified_position_id,
                            "claim": "old curator position",
                            "evidence_type": "verified_position",
                            "source": old_source["document_id"],
                            "locator": old_source["source"],
                            "confidence": 0.75,
                            "inference_level": "low",
                            "permission": "private-local",
                            "chunk_id": old_source["chunk_ids"][0],
                            "document_version": old_source["document_version"],
                        }
                    )
                    + "\n"
                )
            old_quote_ids.add(verified_position_id)
            source.write_text(
                "# Context C\n\n新版本要求必须验证完成标准，并记录回滚路径。\n",
                encoding="utf-8",
            )
            impact = update_pack(pack, [str(source)])
            self.assertEqual(impact["new_source_versions"], 1)
            self.assertEqual(load_pack_metadata(pack)["lifecycle"], load_state(pack))
            manifest = json.loads((pack / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
            versions = [
                item["document_version"]
                for item in manifest["sources"]
                if item["document_id"] == manifest["sources"][-1]["document_id"]
            ]
            self.assertEqual(versions, [1, 2])
            constraints = load_reproducibility(pack)
            self.assertEqual(len(constraints["source_hashes"]), 2)
            new_quote_ids = {
                json.loads(line)["id"]
                for line in (pack / "EVIDENCE_LEDGER.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            }
            self.assertFalse(old_quote_ids & new_quote_ids)
            self.assertTrue(any((pack / "audit" / "history").glob("source-update-*")))
            self.assertEqual(
                [item for item in validate_pack(pack) if item.severity == "error"],
                [],
            )
            self.assertTrue((pack / "reports" / "IMPACT.md").exists())

    def test_independent_model_verification_compiles_profile_skill(self) -> None:
        class FakeProvider:
            def complete_json(self, system: str, user: str, schema_name: str) -> dict:
                del system
                if schema_name.startswith("extract-"):
                    payload = json.loads(user)
                    if schema_name != "extract-assumptions":
                        return {"candidates": []}
                    chunks = payload["chunks"]
                    return {
                        "candidates": [
                            {
                                "title": "verified-bottleneck",
                                "summary": "先识别稀缺资源，再比较单位瓶颈价值。",
                                "tags": ["decision"],
                                "evidence": [
                                    {
                                        "chunk_id": chunk["id"],
                                        "quote": chunk["text"],
                                    }
                                    for chunk in chunks[:2]
                                ],
                            }
                        ]
                    }
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
            skills = verify_and_compile_with_model(pack, FakeProvider())
            self.assertEqual(len(skills), 1)
            self.assertTrue((skills[0] / "SKILL.md").exists())
            self.assertEqual(load_state(pack)["current_phase"], "test")
            self.assertTrue((pack / "audit" / "model-verification.json").exists())
            self.assertTrue((pack / "candidates" / "semantic-candidates.json").exists())
            tests = json.loads((skills[0] / "test-prompts.json").read_text(encoding="utf-8"))
            results = root / "agent-results.json"
            results.write_text(
                json.dumps([{"id": item["id"], "passed": True} for item in tests]),
                encoding="utf-8",
            )
            evaluate_pack(pack, results)
            release = release_pack(pack)
            self.assertEqual(release["status"], "released")
            graph = (pack / "reports" / "EVIDENCE_GRAPH.md").read_text(encoding="utf-8")
            self.assertIn("```mermaid", graph)
            self.assertIn("capability", graph)
            self.assertEqual(load_state(pack)["current_phase"], "evolve")
            installed = install_pack(pack, root / "installed")
            self.assertTrue(Path(installed[0]["destination"]).joinpath("SKILL.md").exists())
            for runtime, prefix in {
                "generic": "skills/",
                "codex": ".codex/skills/",
                "claude": ".claude/skills/",
                "cursor": ".cursor/skills/",
            }.items():
                archive = export_pack(pack, root / "dist", runtime)
                self.assertGreater(archive.stat().st_size, 0)
                with zipfile.ZipFile(archive) as zipped:
                    self.assertTrue(
                        any(name.startswith(prefix) and name.endswith("/SKILL.md") for name in zipped.namelist())
                    )
            self.assertEqual(prepare_darwin(pack)["status"], "prepared")
            manifest = json.loads((pack / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
            source_id = manifest["sources"][0]["source_id"]
            descendants = lineage(root, "source", source_id)
            self.assertIn("skill", {item["to_type"] for item in descendants})
            revocation = revoke_source(root, source_id, "source owner withdrew permission")
            self.assertEqual(revocation["affected_skills"], [skills[0].name])
            regression = json.loads(
                (pack / "reports" / "regression-plan.json").read_text(encoding="utf-8")
            )
            self.assertGreater(regression["count"], 0)
            self.assertEqual(load_state(pack)["phases"]["ship"]["status"], "pending")
            with self.assertRaises(DeliveryError):
                install_pack(pack, root / "installed-after-revoke")

    def test_model_verification_rejects_non_public_pack_without_authorization(self) -> None:
        class UnusedProvider:
            def complete_json(self, system: str, user: str, schema_name: str) -> dict:
                raise AssertionError("provider must not receive private data")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "private.md"
            source.write_text("必须保留这条私人方法和证据，不能外发。" * 10, encoding="utf-8")
            with self.assertRaises(PipelineError):
                create_pack(root, [str(source)], "compliance", "quick", "missing-profile")
            pack = create_pack(
                root,
                [str(source)],
                "methodology",
                "quick",
                "private-method",
                "private-local",
                "self",
            )
            with self.assertRaises(PipelineError):
                verify_and_compile_with_model(pack, UnusedProvider())


class CompilerEvaluationTests(unittest.TestCase):
    def test_profile_template_library_exports_all_builtin_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = export_profile_templates(Path(temporary) / "profiles.json")
            templates = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                set(templates["profiles"]),
                {"content", "methodology", "sop", "tool", "skill", "hybrid"},
            )

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
        for profile in ("content", "methodology", "sop", "tool", "skill", "hybrid"):
            capability = capability_from_candidate(candidate, profile)
            outputs[profile] = (tuple(capability.procedure), tuple(capability.boundaries))
        self.assertEqual(len(set(outputs.values())), 6)

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
            canonical = skill / "evals" / "canonical.json"
            changed = json.loads(canonical.read_text(encoding="utf-8"))
            changed["suite_version"] = "1.0.1"
            canonical.write_text(json.dumps(changed), encoding="utf-8")
            codes = {
                item.code
                for item in validate_pack(pack)
                if item.severity == "error"
            }
            self.assertIn("eval.canonical_drift", codes)
            with self.assertRaises(DeliveryError):
                prepare_darwin(pack)

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
