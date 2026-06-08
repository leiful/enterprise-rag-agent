import unittest
from unittest.mock import patch

from langchain_core.documents import Document

import tools


class BasicToolTests(unittest.TestCase):
    def test_get_time_returns_timestamp(self):
        result = tools.get_time()

        self.assertRegex(result, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_tool_map_exposes_get_time(self):
        tool = tools.get_langchain_tool_map()["get_time"]
        result = tool.invoke({})

        self.assertRegex(result, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


class SearchKnowledgeTests(unittest.TestCase):
    def test_search_knowledge_formats_results(self):
        search_results = [
            Document(
                page_content="Install backend dependencies into .venv.",
                metadata={
                    "score": 0.72,
                    "document_id": "notes.md",
                    "chunk_id": "notes.md_chunk_0002",
                    "chunk_index": 2,
                },
            ),
            Document(
                page_content="Too weak.",
                metadata={
                    "score": 0.28,
                    "document_id": "notes.md",
                    "chunk_id": "notes.md_chunk_0003",
                    "chunk_index": 3,
                },
            ),
        ]

        with patch("tools.KnowledgeBaseRetriever.invoke", return_value=search_results) as search:
            result = tools.search_knowledge("backend dependencies", top_k=9, min_score=0.3)

        search.assert_called_once_with("backend dependencies")
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
        with patch("tools.KnowledgeBaseRetriever.invoke", return_value=[]):
            result = tools.search_knowledge("missing")

        self.assertEqual(
            result,
            "No supported knowledge evidence was found for 'missing' with score >= 0.30. "
            "Tell the user the knowledge base does not contain enough evidence instead of guessing.",
        )

    def test_search_knowledge_result_instructs_grounded_answering(self):
        search_results = [
            Document(
                page_content="Deploy frontend/dist instead of the whole frontend directory.",
                metadata={
                    "score": 0.91,
                    "document_id": "deploy.md",
                    "chunk_id": "deploy.md_chunk_0000",
                    "chunk_index": 0,
                },
            ),
        ]

        with patch("tools.KnowledgeBaseRetriever.invoke", return_value=search_results):
            result = tools.search_knowledge("what should I deploy?")

        self.assertIn("Answer only from relevant snippets.", result)
        self.assertIn("only for claims directly supported by that snippet", result)
        self.assertIn("If the snippets are unrelated or do not fully answer the question", result)
        self.assertIn("[K1] document_id=deploy.md chunk=0 score=0.910", result)

    def test_search_knowledge_schema_discourages_public_figure_queries(self):
        schemas_by_name = {
            tool.name: tool
            for tool in tools.get_langchain_tools()
        }

        description = schemas_by_name["search_knowledge"].description

        self.assertIn("Do not use it for ordinary world-knowledge questions", description)
        self.assertIn("public figures", description)

    def test_tool_map_routes_search_knowledge(self):
        with patch("tools.KnowledgeBaseRetriever.invoke", return_value=[]):
            tool = tools.get_langchain_tool_map()["search_knowledge"]
            result = tool.invoke({"query": "deployment"})

        self.assertIn("No supported knowledge evidence was found for 'deployment'", result)


class ToolSchemaTests(unittest.TestCase):
    def test_schema_names_match_supported_tools(self):
        schema_names = {
            tool.name
            for tool in tools.get_langchain_tools()
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
            tool.name: tool.args_schema.model_json_schema()
            for tool in tools.get_langchain_tools()
        }

        self.assertEqual(
            schemas_by_name["search_knowledge"]["required"],
            ["query"],
        )


if __name__ == "__main__":
    unittest.main()
