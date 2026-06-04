import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tools


class BasicToolTests(unittest.TestCase):
    def test_get_time_returns_timestamp(self):
        result = tools.get_time()

        self.assertRegex(result, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_call_tool_routes_get_time(self):
        with patch("tools.get_time", return_value="now"):
            result = tools.call_tool("get_time", {})

        self.assertEqual(result, "now")

    def test_call_tool_reports_unknown_tool(self):
        result = tools.call_tool("missing_tool", {})

        self.assertEqual(result, "unknown tool: missing_tool")


class SearchKnowledgeTests(unittest.TestCase):
    def test_search_knowledge_formats_results(self):
        search_results = [
            SimpleNamespace(
                score=0.72,
                document_id="notes.md",
                chunk_index=2,
                text="Install backend dependencies into .venv.",
            ),
            SimpleNamespace(
                score=0.28,
                document_id="notes.md",
                chunk_index=3,
                text="Too weak.",
            ),
        ]

        with patch("tools.vector_store.search", return_value=search_results) as search:
            result = tools.search_knowledge("backend dependencies", top_k=9, min_score=0.3)

        search.assert_called_once_with("backend dependencies", top_k=tools.MAX_KNOWLEDGE_RESULTS)
        self.assertIn("Knowledge evidence for 'backend dependencies': 1 result(s).", result)
        self.assertIn("Cite sources with their labels, such as [K1]", result)
        self.assertIn("verify that each snippet is actually about the user's question", result)
        self.assertIn("[K1] document_id=notes.md chunk=2 score=0.720", result)
        self.assertIn("Install backend dependencies into .venv.", result)
        self.assertNotIn("Too weak.", result)

    def test_search_knowledge_requires_query(self):
        result = tools.search_knowledge("")

        self.assertEqual(result, "search_knowledge error: query is required")

    def test_search_knowledge_reports_no_results_above_threshold(self):
        with patch("tools.vector_store.search", return_value=[]):
            result = tools.search_knowledge("missing")

        self.assertEqual(
            result,
            "No supported knowledge evidence was found for 'missing' with score >= 0.30. "
            "Tell the user the knowledge base does not contain enough evidence instead of guessing.",
        )

    def test_search_knowledge_result_instructs_grounded_answering(self):
        search_results = [
            SimpleNamespace(
                score=0.91,
                document_id="deploy.md",
                chunk_index=0,
                text="Deploy frontend/dist instead of the whole frontend directory.",
            ),
        ]

        with patch("tools.vector_store.search", return_value=search_results):
            result = tools.search_knowledge("what should I deploy?")

        self.assertIn("Answer only from relevant snippets.", result)
        self.assertIn("only for claims directly supported by that snippet", result)
        self.assertIn("If the snippets are unrelated or do not fully answer the question", result)
        self.assertIn("[K1] document_id=deploy.md chunk=0 score=0.910", result)

    def test_search_knowledge_schema_discourages_public_figure_queries(self):
        schemas_by_name = {
            tool["function"]["name"]: tool["function"]
            for tool in tools.TOOLS
        }

        description = schemas_by_name["search_knowledge"]["description"]

        self.assertIn("Do not use it for ordinary world-knowledge questions", description)
        self.assertIn("public figures", description)

    def test_call_tool_routes_search_knowledge(self):
        with patch("tools.search_knowledge", return_value="knowledge result"):
            result = tools.call_tool("search_knowledge", {"query": "deployment"})

        self.assertEqual(result, "knowledge result")


class ToolSchemaTests(unittest.TestCase):
    def test_schema_names_match_supported_tools(self):
        schema_names = {
            tool["function"]["name"]
            for tool in tools.TOOLS
        }

        self.assertEqual(
            schema_names,
            {
                "get_time",
                "search_knowledge",
            },
        )

    def test_search_knowledge_schema_requires_query(self):
        schemas_by_name = {
            tool["function"]["name"]: tool["function"]["parameters"]
            for tool in tools.TOOLS
        }

        self.assertEqual(
            schemas_by_name["search_knowledge"]["required"],
            ["query"],
        )


if __name__ == "__main__":
    unittest.main()
