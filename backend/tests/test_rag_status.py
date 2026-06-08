import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

import json
import os
import main


class RagStatusTests(unittest.TestCase):
    def test_rag_status_summarizes_operational_signals(self):
        with patch("main.vector_store.list_documents", return_value=[{"document_id": "notes", "chunk_count": 2}]):
            with patch("main.knowledge_sources.list_sources", return_value=[{"id": 1, "enabled": True, "last_sync_at": None}]):
                with patch("main.get_knowledge_source_file_status_counts", return_value={"indexed": 1, "missing": 1}):
                    with patch("main.get_index_job_status_counts", return_value={"completed": 2, "failed": 1}):
                        with patch("main.get_bm25_stats", return_value={"total_docs": 2, "avg_doc_len": 8.5}):
                            with patch("main.count_knowledge_access_audit", return_value=3):
                                with patch("main.count_admin_audit_events", return_value=5):
                                    with patch("main.summarize_rag_feedback", return_value={"total": 4, "positive": 1, "negative": 3, "by_type": {}}):
                                        with patch("main.latest_rag_eval_report", return_value={"available": False}):
                                            data = main.get_rag_operational_status()

        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["documents"]["count"], 1)
        self.assertEqual(data["documents"]["chunk_count"], 2)
        self.assertEqual(data["sources"]["file_status_counts"]["missing"], 1)
        self.assertEqual(data["index_jobs"]["status_counts"]["failed"], 1)
        self.assertEqual(data["retrieval"]["bm25_total_docs"], 2)
        self.assertEqual(data["retrieval"]["default_top_k"], main.DEFAULT_KNOWLEDGE_TOP_K)
        self.assertEqual(data["retrieval"]["default_min_score"], main.DEFAULT_KNOWLEDGE_MIN_SCORE)
        self.assertTrue(data["retrieval"]["require_document_department"])
        self.assertIn("ocr_available", data["parsing"])
        self.assertEqual(data["audit"]["event_count"], 3)
        self.assertEqual(data["audit"]["admin_event_count"], 5)
        self.assertEqual(data["feedback"]["negative"], 3)
        self.assertEqual(
            {issue["name"] for issue in data["issues"]},
            {"failed_index_jobs", "missing_source_files", "unsynced_sources"},
        )

    def test_latest_rag_eval_report_summarizes_metrics(self):
        with TemporaryDirectory() as temp_dir:
            backend_dir = Path(temp_dir) / "backend"
            reports_dir = Path(temp_dir) / "rag_eval" / "reports"
            backend_dir.mkdir()
            reports_dir.mkdir(parents=True)
            report_path = reports_dir / "rag_eval_20260608-010203.json"
            report_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "q1",
                            "question": "Where is the port?",
                            "expected_docs": "notes.md",
                            "expected_hit": True,
                            "expected_rank": 1,
                            "top1_hit": True,
                            "unexpected_sources": False,
                            "answer": "Use [K1].",
                            "answer_has_citation": True,
                            "top_document": "notes.md",
                        },
                        {
                            "id": "q2",
                            "question": "Unknown?",
                            "expected_docs": "",
                            "expected_hit": False,
                            "expected_rank": "",
                            "top1_hit": False,
                            "unexpected_sources": True,
                            "answer": "",
                            "answer_has_citation": False,
                            "top_document": "notes.md",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(main, "__file__", str(backend_dir / "main.py")):
                data = main.latest_rag_eval_report()

        self.assertTrue(data["available"])
        self.assertEqual(data["summary"]["total"], 2)
        self.assertEqual(data["summary"]["expected_hits"], 1)
        self.assertEqual(data["summary"]["unexpected_sources"], 1)
        self.assertEqual(data["summary"]["failed_count"], 1)

    def test_latest_rag_eval_report_includes_strict_failure_reasons(self):
        with TemporaryDirectory() as temp_dir:
            backend_dir = Path(temp_dir) / "backend"
            reports_dir = Path(temp_dir) / "rag_eval" / "reports"
            backend_dir.mkdir()
            reports_dir.mkdir(parents=True)
            report_path = reports_dir / "rag_eval_20260608-010203.json"
            report_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "q1",
                            "expected_docs": "notes.md",
                            "expected_hit": False,
                            "unexpected_sources": False,
                            "strict_failure": True,
                            "failure_reasons": ["expected_source_missed"],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(main, "__file__", str(backend_dir / "main.py")):
                data = main.latest_rag_eval_report()

        self.assertEqual(data["summary"]["strict_failures"], 1)
        self.assertEqual(data["summary"]["failure_reasons"]["expected_source_missed"], 1)

    def test_latest_rag_eval_report_reads_latest_manual_report(self):
        with TemporaryDirectory() as temp_dir:
            backend_dir = Path(temp_dir) / "backend"
            reports_dir = Path(temp_dir) / "rag_eval" / "reports"
            backend_dir.mkdir()
            reports_dir.mkdir(parents=True)
            old_report_path = reports_dir / "rag_eval_20260608-010203.json"
            manual_report_path = reports_dir / "manual_eval_20260608-020304.json"
            old_report_path.write_text("[]", encoding="utf-8")
            manual_report_path.write_text(
                json.dumps(
                    {
                        "summary": {
                            "total": 2,
                            "average_score": 4.08,
                            "expected_doc_hit_rate": 50,
                            "abstention_accuracy": 0,
                        },
                        "results": [
                            {
                                "id": "direct_001",
                                "question": "How do I upload knowledge?",
                                "expected_docs": ["03_knowledge_workflow.md"],
                                "expected_doc_hit": True,
                                "k1_document": "03_knowledge_workflow.md",
                                "score": 8,
                            },
                            {
                                "id": "direct_002",
                                "question": "Who owns billing?",
                                "expected_docs": ["05_limitations_and_roadmap.md"],
                                "expected_doc_hit": False,
                                "k1_document": "07_auth_and_storage.md",
                                "score": 5,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            old_time = 1_717_782_000
            new_time = 1_717_782_100
            os.utime(old_report_path, (old_time, old_time))
            os.utime(manual_report_path, (new_time, new_time))

            with patch.object(main, "__file__", str(backend_dir / "main.py")):
                data = main.latest_rag_eval_report()

        self.assertTrue(data["available"])
        self.assertEqual(data["report"]["name"], "manual_eval_20260608-020304.json")
        self.assertEqual(data["summary"]["total"], 2)
        self.assertEqual(data["summary"]["average_score"], 4.08)
        self.assertEqual(data["summary"]["expected_hits"], 1)
        self.assertEqual(data["summary"]["failed_count"], 1)
        self.assertEqual(data["failed_rows"][0]["top_document"], "07_auth_and_storage.md")

    def test_rag_eval_suite_list_exposes_three_curated_suites(self):
        suites = main.rag_eval_suite_list()

        self.assertEqual(
            [suite["id"] for suite in suites],
            ["core", "acceptance", "ragbench"],
        )
        self.assertEqual([suite["question_count"] for suite in suites], [20, 12, 5])

    def test_run_rag_eval_suite_writes_suite_report(self):
        with TemporaryDirectory() as temp_dir:
            backend_dir = Path(temp_dir) / "backend"
            docs_dir = Path(temp_dir) / "docs"
            reports_dir = Path(temp_dir) / "rag_eval" / "reports"
            questions_path = Path(temp_dir) / "questions.json"
            backend_dir.mkdir()
            docs_dir.mkdir()
            reports_dir.mkdir(parents=True)
            (docs_dir / "notes.md").write_text("Notes", encoding="utf-8")
            questions_path.write_text(
                json.dumps([
                    {
                        "id": "q1",
                        "question": "Where are the notes?",
                        "expected_docs": ["notes.md"],
                    }
                ]),
                encoding="utf-8",
            )
            suite = {
                "id": "tiny",
                "name": "Tiny",
                "description": "Tiny suite",
                "docs_dir": docs_dir,
                "questions": questions_path,
                "top_k": 1,
                "min_score": 0.1,
            }

            def fake_search(query, top_k, min_score, client=None):
                return {
                    "results": [
                        {
                            "document_id": "notes.md",
                            "chunk_index": 0,
                            "score": 0.9,
                        }
                    ]
                }

            with patch.object(main, "__file__", str(backend_dir / "main.py")):
                with patch.dict(main.RAG_EVAL_SUITES, {"tiny": suite}, clear=True):
                    with patch("main.index_rag_eval_docs", return_value=[]):
                        with patch("main.search_knowledge_payload", side_effect=fake_search):
                            data = main.run_rag_eval_suite("tiny")

        self.assertEqual(data["suite"]["id"], "tiny")
        self.assertTrue(data["report"]["name"].startswith("rag_eval_tiny_"))
        self.assertEqual(data["summary"]["recall_at_k"], 1)


class KnowledgeSearchScopeTests(unittest.TestCase):
    def test_search_knowledge_passes_user_department_scope(self):
        user = {
            "id": 2,
            "username": "analyst",
            "role": "user",
            "departments": ["Finance"],
        }
        request = main.SearchKnowledgeRequest(query="policy", top_k=1)
        access_stats = {"candidate_count": 3, "access_filtered_count": 1}

        with patch("main.search_knowledge_payload", return_value={"kept_results": [], "access_stats": access_stats}) as search_mock:
            with patch("main.add_knowledge_access_audit") as audit_mock:
                response = main.search_knowledge(request, user=user)

        self.assertEqual(response["results"], [])
        self.assertEqual(response["evidence_status"], "insufficient")
        self.assertEqual(response["access_stats"], access_stats)
        self.assertEqual(search_mock.call_args.kwargs["departments"], ["Finance"])
        self.assertEqual(audit_mock.call_args.kwargs["access_stats"], access_stats)


if __name__ == "__main__":
    unittest.main()
