import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AIMessageChunk

from AI_agent import (
    KNOWLEDGE_PREFLIGHT_PREFIX,
    build_knowledge_preflight,
    build_user_message_with_knowledge_preflight,
    main,
    rerank_with_dashscope,
    run_agent,
    run_agent_stream,
    run_tool_call,
    search_knowledge_results,
)
from config import NO_EVIDENCE_ANSWER, SYSTEM_MESSAGE
from vector_store import SearchResult


def knowledge_preflight(text="No supported knowledge evidence was found.", sources=None):
    return {
        "content": (
            f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
            f"{text}\n\n"
            "User question:\n"
            "patched question"
        ),
        "sources": sources or [],
    }


def make_tool_call(name, arguments):
    return {
        "id": f"call_{name}",
        "name": name,
        "args": arguments,
        "type": "tool_call",
    }


def make_message(content="", tool_calls=None):
    tool_calls = tool_calls or []

    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        model_dump=lambda exclude_none=True: {
            "role": "assistant",
            "content": content,
            **({"tool_calls": tool_calls} if tool_calls else {}),
        },
    )


class FakeLangChainClient:
    def __init__(self, responses=None, stream_chunks=None):
        self.responses = list(responses or [])
        self.stream_chunks = list(stream_chunks or [])
        self.invoked_messages = []
        self.stream_messages = []

    def invoke(self, messages, **kwargs):
        self.invoked_messages.append(messages)
        return self.responses.pop(0)

    def stream(self, messages):
        self.stream_messages.append(messages)
        return iter(self.stream_chunks)


class RunToolCallTests(unittest.TestCase):
    def test_get_time_returns_result(self):
        tool_call = make_tool_call("get_time", {})

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 10)

        self.assertEqual(tool_args, {})
        self.assertRegex(tool_result, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertEqual(remaining_lines, 10)
        self.assertFalse(denied_by_user)

    def test_missing_required_argument_returns_clear_error(self):
        tool_call = make_tool_call("search_knowledge", {})

        tool_args, tool_result, remaining_lines, denied_by_user = run_tool_call(tool_call, 10)

        self.assertEqual(tool_args, {})
        self.assertEqual(
            tool_result,
            "search_knowledge error: missing required argument 'query'.",
        )
        self.assertEqual(remaining_lines, 10)
        self.assertFalse(denied_by_user)


class RunAgentTests(unittest.TestCase):
    def test_build_user_message_with_knowledge_preflight(self):
        with patch(
            "AI_agent.build_knowledge_preflight",
            return_value={
                "content": (
                    f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                    "No supported knowledge evidence was found.\n\n"
                    "User question:\n"
                    "who is trump?"
                ),
                "sources": [],
            },
        ):
            message = build_user_message_with_knowledge_preflight("who is trump?")

        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, message)
        self.assertIn("No supported knowledge evidence was found.", message)
        self.assertIn("User question:\nwho is trump?", message)

    def test_run_agent_returns_answer_from_lcel_chain(self):
        client = FakeLangChainClient(responses=[AIMessage(content="The current time was checked.")])
        messages = [{"role": "system", "content": "test"}]
        preflight = {
            "content": (
                f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                "No supported knowledge evidence was found.\n\n"
                "User question:\n"
                "what time is it?"
            ),
            "sources": [],
        }

        with patch("AI_agent.STRICT_KNOWLEDGE_ABSTENTION", False):
            with patch("services.agent_runtime.append_log_entries"):
                with redirect_stdout(StringIO()):
                    answer = run_agent(client, messages, "what time is it?", knowledge_preflight=preflight)

        self.assertEqual(answer, "The current time was checked.")
        self.assertEqual(len(client.responses), 0)
        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, messages[1]["content"])
        self.assertIn("User question:\nwhat time is it?", messages[1]["content"])
        prompt_messages = client.invoked_messages[0].to_messages()
        self.assertEqual(prompt_messages[0].type, "system")
        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, prompt_messages[-1].content)

    def test_run_agent_strictly_abstains_without_sources(self):
        client = FakeLangChainClient(responses=[AIMessage(content="Knowledge base has no evidence. Trump is...")])
        messages = [{"role": "system", "content": "test"}]
        preflight = {
            "content": (
                f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                "No supported knowledge evidence was found.\n\n"
                "User question:\n"
                "who is trump?"
            ),
            "sources": [],
        }

        with redirect_stdout(StringIO()):
            with patch("services.agent_runtime.append_log_entries"):
                answer = run_agent(client, messages, "who is trump?", knowledge_preflight=preflight)

        self.assertEqual(answer, "知识库中没有足够的相关证据支持回答这个问题。")
        self.assertEqual(len(client.invoked_messages), 0)
        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, messages[1]["content"])

    def test_run_agent_stream_streams_final_answer_after_tool_check(self):
        client = FakeLangChainClient(
            stream_chunks=[AIMessageChunk(content="hello "), AIMessageChunk(content="there")],
        )
        messages = [{"role": "system", "content": "test"}]
        preflight = {
            "content": (
                f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                "No supported knowledge evidence was found.\n\n"
                "User question:\n"
                "hello"
            ),
            "sources": [],
        }

        with patch("AI_agent.STRICT_KNOWLEDGE_ABSTENTION", False):
            with patch("services.agent_runtime.append_log_entries"):
                answer = "".join(run_agent_stream(client, messages, "hello", knowledge_preflight=preflight))

        self.assertEqual(answer, "hello there")
        self.assertEqual(messages[-1], {"role": "assistant", "content": "hello there"})
        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, messages[1]["content"])
        prompt_messages = client.stream_messages[0].to_messages()
        self.assertIn(KNOWLEDGE_PREFLIGHT_PREFIX, prompt_messages[-1].content)

    def test_build_knowledge_preflight_uses_rewritten_query_in_lcel_retrieval(self):
        messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "之前的问题"},
        ]
        documents = [
            Document(
                page_content="Deploy frontend/dist instead of the whole frontend directory.",
                metadata={
                    "score": 0.91,
                    "chunk_id": "deploy.md_chunk_0000",
                    "document_id": "deploy.md",
                    "chunk_index": 0,
                },
            ),
        ]

        with patch("chains.retrieval_chain.ENABLE_QUERY_REWRITE", True):
            with patch("chains.retrieval_chain.rewrite_query_with_history", return_value="改写后的问题"):
                with patch("chains.retrieval_chain.KnowledgeBaseRetriever.invoke", return_value=documents) as invoke_mock:
                    result = build_knowledge_preflight("原问题", client=object(), messages=messages)

        invoke_mock.assert_called_once_with("改写后的问题")
        self.assertIn("Knowledge evidence for '改写后的问题'", result["content"])
        self.assertIn("Start the final answer by explicitly saying that the following information comes from the knowledge base materials.", result["content"])
        self.assertIn("Query was rewritten from: '原问题' to: '改写后的问题'", result["content"])
        self.assertEqual(result["sources"][0]["document_id"], "deploy.md")

    def test_build_knowledge_preflight_includes_enterprise_source_metadata(self):
        documents = [
            Document(
                page_content="Finance approval requires two reviewers.",
                metadata={
                    "score": 0.91,
                    "chunk_id": "finance.md_chunk_0000",
                    "document_id": "finance.md",
                    "chunk_index": 0,
                    "department": "Finance",
                    "sensitivity": "internal",
                    "version": "2026.1",
                },
            ),
        ]

        with patch("chains.retrieval_chain.KnowledgeBaseRetriever.invoke", return_value=documents):
            result = build_knowledge_preflight("approval policy", client=object(), messages=[])

        self.assertIn("metadata: department=Finance sensitivity=internal version=2026.1", result["content"])


class RerankTests(unittest.TestCase):
    def test_dashscope_rerank_orders_candidates_and_filters_low_scores(self):
        candidates = [
            SearchResult(0.1, "chunk-a", "doc-a", 0, "weak evidence"),
            SearchResult(0.2, "chunk-b", "doc-b", 1, "strong evidence"),
            SearchResult(0.3, "chunk-c", "doc-c", 2, "barely related"),
        ]

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return (
                    b'{"output":{"results":['
                    b'{"index":1,"relevance_score":0.91},'
                    b'{"index":2,"relevance_score":0.05},'
                    b'{"index":0,"relevance_score":0.44}'
                    b']}}'
                )

        with patch("services.rerank_service.RERANK_API_KEY", "test-key"):
            with patch("services.rerank_service.RERANK_MIN_SCORE", 0.2):
                with patch("services.rerank_service.urlopen", return_value=FakeResponse()):
                    results = rerank_with_dashscope("question", candidates, top_k=3)

        self.assertEqual(
            [result.chunk_id for result in results],
            ["chunk-b", "chunk-a"],
        )
        self.assertEqual(results[0].score, 0.91)
        self.assertEqual(results[1].score, 0.44)

    def test_dashscope_rerank_keeps_ranked_results_if_min_score_removes_all(self):
        candidates = [
            SearchResult(0.1, "chunk-a", "doc-a", 0, "weak evidence"),
            SearchResult(0.2, "chunk-b", "doc-b", 1, "related evidence"),
        ]

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return (
                    b'{"output":{"results":['
                    b'{"index":1,"relevance_score":0.05},'
                    b'{"index":0,"relevance_score":0.04}'
                    b']}}'
                )

        with patch("services.rerank_service.RERANK_API_KEY", "test-key"):
            with patch("services.rerank_service.RERANK_MIN_SCORE", 0.2):
                with patch("services.rerank_service.urlopen", return_value=FakeResponse()):
                    results = rerank_with_dashscope("question", candidates, top_k=2)

        self.assertEqual([result.chunk_id for result in results], ["chunk-b", "chunk-a"])

    def test_search_knowledge_results_uses_rerank_gate(self):
        candidates = [
            Document(page_content="first", metadata={"score": 0.8, "chunk_id": "chunk-a", "document_id": "doc-a", "chunk_index": 0}),
            Document(page_content="second", metadata={"score": 0.7, "chunk_id": "chunk-b", "document_id": "doc-b", "chunk_index": 1}),
            Document(page_content="third", metadata={"score": 0.6, "chunk_id": "chunk-c", "document_id": "doc-c", "chunk_index": 2}),
            Document(page_content="fourth", metadata={"score": 0.5, "chunk_id": "chunk-d", "document_id": "doc-d", "chunk_index": 3}),
        ]

        with patch("chains.retrieval_chain.ENABLE_RERANK", True):
            with patch("chains.retrieval_chain.RERANK_MIN_CANDIDATES", 1):
                with patch("chains.retrieval_chain.KnowledgeBaseRetriever.invoke", return_value=candidates):
                    with patch(
                        "services.knowledge_runtime.rerank_with_dashscope",
                        return_value=[SearchResult(0.7, "chunk-b", "doc-b", 1, "second")],
                    ):
                        results = search_knowledge_results(
                            "question",
                            top_k=1,
                            min_score=0.75,
                        )

        self.assertEqual(results, [])

    def test_search_knowledge_results_filters_uncovered_query_terms(self):
        candidates = [
            Document(
                page_content="Session storage uses PostgreSQL tables.",
                metadata={"score": 0.95, "chunk_id": "chunk-a", "document_id": "auth.md", "chunk_index": 0},
            ),
            Document(
                page_content="The mobile billing workflow is not documented here.",
                metadata={"score": 0.8, "chunk_id": "chunk-b", "document_id": "billing.md", "chunk_index": 1},
            ),
        ]

        with patch("chains.retrieval_chain.ENABLE_QUERY_COVERAGE_FILTER", True):
            with patch("chains.retrieval_chain.KnowledgeBaseRetriever.invoke", return_value=candidates):
                results = search_knowledge_results(
                    "mobile billing workflow",
                    top_k=2,
                    min_score=0.1,
                    use_multi_query=False,
                )

        self.assertEqual([result.document_id for result in results], ["billing.md"])

    def test_search_knowledge_results_keeps_candidates_if_coverage_filter_removes_all(self):
        candidates = [
            Document(
                page_content="Knowledge-base file upload, indexing, and source citations are supported.",
                metadata={"score": 0.95, "chunk_id": "chunk-a", "document_id": "overview.md", "chunk_index": 0},
            ),
        ]

        with patch("chains.retrieval_chain.ENABLE_QUERY_COVERAGE_FILTER", True):
            with patch("chains.retrieval_chain.KnowledgeBaseRetriever.invoke", return_value=candidates):
                results = search_knowledge_results(
                    "main features of this AI agent project",
                    top_k=1,
                    min_score=0.1,
                    use_multi_query=False,
                )

        self.assertEqual([result.document_id for result in results], ["overview.md"])


class MainTests(unittest.TestCase):
    def test_main_prints_startup_error_when_api_key_is_missing(self):
        output = StringIO()

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            with redirect_stdout(output):
                main()

        self.assertIn(
            "Startup error: Missing DEEPSEEK_API_KEY. Please set it in .env.",
            output.getvalue(),
        )


class SystemMessageTests(unittest.TestCase):
    def test_system_message_requires_cited_knowledge_answers(self):
        content = SYSTEM_MESSAGE["content"]

        self.assertIn("Every user message includes a Knowledge base preflight result", content)
        self.assertIn("begin by saying the knowledge base does not contain enough relevant evidence", content)
        self.assertIn("explicitly tell the user that the answer is based on the knowledge base materials", content)
        self.assertIn("Only cite the provided source labels such as [K1]", content)
        self.assertIn("Do not add unsupported details", content)


if __name__ == "__main__":
    unittest.main()
