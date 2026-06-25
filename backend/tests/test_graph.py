import unittest
from unittest.mock import patch

from graph.graph import build_agent_graph, should_abstain
from graph.state import AgentState


class _FakeChain:
    def __init__(self, client):
        self._client = client

    def invoke(self, inputs, config=None):
        return {
            "answer": f"answered by {self._client}",
            "knowledge_preflight": inputs.get("knowledge_preflight") or {"sources": [], "content": "preflight"},
        }


def identity_chain(client):
    return _FakeChain(client)


def _noop_extract(content):
    return content


def _fake_rerank(query, candidates, top_k=None):
    return candidates


_test_graph_kwargs = {
    "extract_text_content": _noop_extract,
    "knowledge_preflight_prefix": "Knowledge base preflight result:",
    "rerank_with_dashscope": _fake_rerank,
}


class ShouldAbstainTests(unittest.TestCase):
    def test_abstains_when_strict_and_no_sources(self):
        with patch("graph.graph.STRICT_KNOWLEDGE_ABSTENTION", True):
            self.assertTrue(should_abstain({"sources": [], "content": "no evidence"}))

    def test_not_abstain_when_strict_disabled(self):
        with patch("graph.graph.STRICT_KNOWLEDGE_ABSTENTION", False):
            preflight = {"sources": [], "content": "no evidence"}
            self.assertFalse(should_abstain(preflight))

    def test_not_abstain_when_strict_and_has_sources(self):
        with patch("graph.graph.STRICT_KNOWLEDGE_ABSTENTION", True):
            preflight = {"sources": [{"document_id": "doc.md"}], "content": "has evidence"}
            self.assertFalse(should_abstain(preflight))

    def test_not_abstain_when_preflight_is_none(self):
        with patch("graph.graph.STRICT_KNOWLEDGE_ABSTENTION", True):
            self.assertFalse(should_abstain(None))


class BuildAgentGraphTests(unittest.TestCase):
    def test_abstain_route_returns_no_evidence_answer(self):
        from config import NO_EVIDENCE_ANSWER
        graph = build_agent_graph(identity_chain, **_test_graph_kwargs)
        result = graph.invoke({
            "_client": "test-client",
            "_return_sources": False,
            "messages": [{"role": "system", "content": "test"}],
            "user_input": "question",
            "knowledge_preflight": {"sources": [], "content": "no evidence"},
            "answer": "",
            "sources": [],
        })
        self.assertEqual(result["answer"], NO_EVIDENCE_ANSWER)
        self.assertEqual(result["_route"], "abstain")

    def test_run_rag_route_returns_chain_answer(self):
        graph = build_agent_graph(identity_chain, **_test_graph_kwargs)
        result = graph.invoke({
            "_client": "test-client",
            "_return_sources": False,
            "messages": [{"role": "system", "content": "test"}],
            "user_input": "question",
            "knowledge_preflight": {"sources": [{"document_id": "doc.md"}], "content": "has evidence"},
            "answer": "",
            "sources": [],
        })
        self.assertEqual(result["answer"], "answered by test-client")
        self.assertEqual(result["_route"], "run_rag")

    def test_run_rag_route_with_return_sources(self):
        graph = build_agent_graph(identity_chain, **_test_graph_kwargs)
        result = graph.invoke({
            "_client": "test-client",
            "_return_sources": True,
            "messages": [{"role": "system", "content": "test"}],
            "user_input": "question",
            "knowledge_preflight": {"sources": [{"document_id": "doc.md"}], "content": "has evidence"},
            "answer": "",
            "sources": [],
        })
        self.assertEqual(result["answer"], "answered by test-client")
        self.assertEqual(result["_route"], "run_rag")

    def test_skips_retrieval_when_preflight_provided(self):
        from config import NO_EVIDENCE_ANSWER
        graph = build_agent_graph(identity_chain, **_test_graph_kwargs)
        result = graph.invoke({
            "_client": "test-client",
            "_return_sources": False,
            "messages": [{"role": "system", "content": "test"}],
            "user_input": "question",
            "knowledge_preflight": {"sources": [{"document_id": "doc.md"}], "content": "has evidence"},
            "answer": "",
            "sources": [],
        })
        self.assertEqual(result["_route"], "run_rag")
        self.assertNotIn("query_to_search", result, "should not run retrieval when preflight is provided")

    def test_full_retrieval_pipeline_routes_correctly(self):
        from unittest.mock import patch
        graph = build_agent_graph(identity_chain, **_test_graph_kwargs)
        with patch("graph.graph.retrieve_ranked_results") as mock_retrieve:
            mock_retrieve.return_value = {
                "kept_results": [],
                "access_stats": {"candidate_count": 0},
            }
            result = graph.invoke({
                "_client": "test-client",
                "_return_sources": False,
                "messages": [{"role": "system", "content": "test"}],
                "user_input": "question",
                "knowledge_preflight": None,
                "category": None,
                "tags": None,
                "file_extensions": None,
                "departments": None,
                "use_multi_query": None,
                "answer": "",
                "sources": [],
            })
        self.assertEqual(result["_route"], "run_rag")
        mock_retrieve.assert_called_once()

    def test_retrieval_route_processes_query_then_retrieves_then_formats(self):
        from unittest.mock import patch
        graph = build_agent_graph(identity_chain, **_test_graph_kwargs)
        with patch("graph.graph.resolve_retrieval_payload") as mock_resolve:
            mock_resolve.return_value = {
                "query_to_search": "rewritten question",
                "queries_to_search": ["rewritten question", "q2"],
            }
            with patch("graph.graph.retrieve_ranked_results") as mock_retrieve:
                mock_retrieve.return_value = {
                    "kept_results": [],
                    "access_stats": {"candidate_count": 5},
                }
                result = graph.invoke({
                    "_client": "test-client",
                    "_return_sources": False,
                    "messages": [{"role": "system", "content": "test"}],
                    "user_input": "question",
                    "knowledge_preflight": None,
                    "category": None,
                    "tags": None,
                    "file_extensions": None,
                    "departments": None,
                    "use_multi_query": None,
                    "answer": "",
                    "sources": [],
                })
        self.assertEqual(result["_route"], "run_rag")
        mock_resolve.assert_called_once()
        mock_retrieve.assert_called_once()
        self.assertIn("knowledge_preflight", result)
        self.assertIn("content", result["knowledge_preflight"])

    def test_messages_mutated_by_run_rag_route(self):
        messages = [{"role": "system", "content": "test"}]
        graph = build_agent_graph(identity_chain, **_test_graph_kwargs)
        graph.invoke({
            "_client": "test-client",
            "_return_sources": False,
            "messages": messages,
            "user_input": "question",
            "knowledge_preflight": {"sources": [{"document_id": "doc.md"}], "content": "has evidence"},
            "answer": "",
            "sources": [],
        })
        self.assertGreater(len(messages), 1)


if __name__ == "__main__":
    unittest.main()
