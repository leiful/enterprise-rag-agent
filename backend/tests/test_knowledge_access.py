import unittest
from unittest.mock import patch

from knowledge_access import can_access_document, document_lifecycle_status
from langchain_retriever import KnowledgeBaseRetriever
from vector_store import SearchResult
import langchain_retriever


class KnowledgeAccessPolicyTests(unittest.TestCase):
    def test_admin_scope_allows_any_department(self):
        self.assertTrue(can_access_document({"department": "Finance"}, None))

    def test_user_scope_allows_explicit_public_documents(self):
        self.assertTrue(can_access_document({"sensitivity": "public"}, []))

    def test_user_scope_rejects_unclassified_documents_by_default(self):
        self.assertFalse(can_access_document({}, []))
        self.assertFalse(can_access_document({"department": ""}, ["HR"]))

    def test_user_scope_allows_matching_department_case_insensitive(self):
        self.assertTrue(can_access_document({"department": "Finance"}, ["finance"]))

    def test_user_scope_rejects_other_department(self):
        self.assertFalse(can_access_document({"department": "Legal"}, ["Finance"]))

    def test_document_lifecycle_status_detects_inactive_documents(self):
        self.assertEqual(document_lifecycle_status({"expiry_date": "2000-01-01"}), "expired")
        self.assertEqual(document_lifecycle_status({"effective_date": "2999-01-01"}), "not_yet_effective")
        self.assertEqual(document_lifecycle_status({"effective_date": "2000-01-01"}), "active")
        self.assertEqual(document_lifecycle_status({"status": "draft"}), "draft")
        self.assertEqual(document_lifecycle_status({"status": "archived"}), "archived")


class KnowledgeRetrieverAccessTests(unittest.TestCase):
    def test_retriever_keeps_explicit_public_and_matching_department_documents(self):
        results = [
            SearchResult(0.9, "public_chunk", "public.md", 0, "public handbook"),
            SearchResult(0.8, "finance_chunk", "finance.md", 0, "finance policy"),
            SearchResult(0.7, "legal_chunk", "legal.md", 0, "legal policy"),
        ]
        metadata = {
            "public.md": {"sensitivity": "public"},
            "finance.md": {"department": "Finance"},
            "legal.md": {"department": "Legal"},
        }

        with patch("langchain_retriever.vector_store.hybrid_search", return_value=results):
            with patch("langchain_retriever.vector_store.get_document_metadata", side_effect=lambda document_id: metadata[document_id]):
                documents = KnowledgeBaseRetriever(departments=["finance"]).invoke("policy")

        self.assertEqual(
            [document.metadata["document_id"] for document in documents],
            ["public.md", "finance.md"],
        )

    def test_retriever_records_access_filter_stats(self):
        results = [
            SearchResult(0.9, "finance_chunk", "finance.md", 0, "finance policy"),
            SearchResult(0.7, "legal_chunk", "legal.md", 0, "legal policy"),
        ]
        metadata = {
            "finance.md": {"department": "Finance"},
            "legal.md": {"department": "Legal"},
        }

        retriever = KnowledgeBaseRetriever(departments=["finance"])
        with patch("langchain_retriever.vector_store.hybrid_search", return_value=results):
            with patch("langchain_retriever.vector_store.get_document_metadata", side_effect=lambda document_id: metadata[document_id]):
                documents = retriever.invoke("policy")

        self.assertEqual(len(documents), 1)
        self.assertEqual(retriever.last_access_stats["candidate_count"], 2)
        self.assertEqual(retriever.last_access_stats["access_filtered_count"], 1)
        self.assertEqual(retriever.last_access_stats["kept_count"], 1)

    def test_retriever_uses_enterprise_hybrid_weights_by_default(self):
        with patch("langchain_retriever.vector_store.hybrid_search", return_value=[]) as search_mock:
            KnowledgeBaseRetriever().invoke("policy")

        self.assertEqual(search_mock.call_args.kwargs["bm25_weight"], langchain_retriever.HYBRID_BM25_WEIGHT)
        self.assertEqual(search_mock.call_args.kwargs["vector_weight"], langchain_retriever.HYBRID_VECTOR_WEIGHT)

    def test_retriever_filters_inactive_documents(self):
        results = [
            SearchResult(0.9, "active_chunk", "active.md", 0, "active policy"),
            SearchResult(0.8, "expired_chunk", "expired.md", 0, "expired policy"),
        ]
        metadata = {
            "active.md": {"effective_date": "2000-01-01"},
            "expired.md": {"expiry_date": "2000-01-01"},
        }

        retriever = KnowledgeBaseRetriever()
        with patch("langchain_retriever.vector_store.hybrid_search", return_value=results):
            with patch("langchain_retriever.vector_store.get_document_metadata", side_effect=lambda document_id: metadata[document_id]):
                documents = retriever.invoke("policy")

        self.assertEqual([document.metadata["document_id"] for document in documents], ["active.md"])
        self.assertEqual(retriever.last_access_stats["inactive_filtered_count"], 1)

    def test_retriever_prefers_latest_version_in_same_group(self):
        results = [
            SearchResult(0.95, "old_chunk", "policy_v1.md", 0, "old policy"),
            SearchResult(0.80, "new_chunk", "policy_v2.md", 0, "new policy"),
        ]
        metadata = {
            "policy_v1.md": {"canonical_id": "policy", "version": "1.0", "effective_date": "2024-01-01"},
            "policy_v2.md": {"canonical_id": "policy", "version": "2.0", "effective_date": "2025-01-01"},
        }

        retriever = KnowledgeBaseRetriever()
        with patch("langchain_retriever.vector_store.hybrid_search", return_value=results):
            with patch("langchain_retriever.vector_store.get_document_metadata", side_effect=lambda document_id: metadata[document_id]):
                documents = retriever.invoke("policy")

        self.assertEqual([document.metadata["document_id"] for document in documents], ["policy_v2.md"])
        self.assertEqual(retriever.last_access_stats["older_version_filtered_count"], 1)


if __name__ == "__main__":
    unittest.main()
