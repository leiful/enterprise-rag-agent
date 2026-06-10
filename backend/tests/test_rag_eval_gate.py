import unittest
from argparse import Namespace
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.rag_eval import evaluate_quality_gate, summarize_rows


class RagEvalGateTests(unittest.TestCase):
    def test_quality_gate_reports_failed_thresholds(self):
        rows = [
            {
                "expected_docs": "policy.md",
                "expected_hit": False,
                "expected_rank": "",
                "top1_hit": False,
                "unexpected_sources": False,
                "answer": "No citation",
                "answer_has_citation": False,
                "strict_failure": True,
                "failure_reasons": ["expected_source_missed"],
            },
            {
                "expected_docs": "",
                "expected_hit": False,
                "expected_rank": "",
                "top1_hit": False,
                "unexpected_sources": True,
                "answer": "",
                "answer_has_citation": False,
                "strict_failure": True,
                "failure_reasons": ["unexpected_source_for_unknown"],
            },
        ]
        summary = summarize_rows(rows)
        args = Namespace(
            min_recall=1.0,
            min_top1=0.8,
            min_mrr=0.9,
            min_citation_rate=0.9,
            min_abstention_accuracy=1.0,
            max_strict_failures=0,
            max_unexpected_sources=0,
        )

        failures = evaluate_quality_gate(summary, args)

        self.assertIn("recall_at_k 0.000 < 1.000", failures)
        self.assertIn("unexpected_sources 1 > 0", failures)

    def test_summary_includes_evidence_hit_rate(self):
        rows = [
            {
                "expected_docs": "policy.md",
                "expected_hit": True,
                "expected_rank": 1,
                "top1_hit": True,
                "unexpected_sources": False,
                "answer": "",
                "answer_has_citation": False,
                "strict_failure": False,
                "failure_reasons": [],
                "evidence_terms_hit": True,
            },
            {
                "expected_docs": "policy.md",
                "expected_hit": True,
                "expected_rank": 1,
                "top1_hit": True,
                "unexpected_sources": False,
                "answer": "",
                "answer_has_citation": False,
                "strict_failure": True,
                "failure_reasons": ["evidence_terms_missing"],
                "evidence_terms_hit": False,
            },
        ]

        summary = summarize_rows(rows)

        self.assertEqual(summary["evidence_hits"], 1)
        self.assertEqual(summary["evidence_total"], 2)
        self.assertEqual(summary["evidence_hit_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
