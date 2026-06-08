import unittest
from unittest.mock import patch
from types import SimpleNamespace

import vector_store
from tests.test_db_utils import patched_postgres_database


class FakeEmbeddingClient:
    vocabulary = [
        "agent",
        "tool",
        "memory",
        "vector",
        "database",
        "weather",
        "pork",
    ]

    def embed(self, texts):
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text):
        tokens = text.lower().replace(".", " ").replace(",", " ").split()
        return [tokens.count(token) for token in self.vocabulary]


class VectorStoreTests(unittest.TestCase):
    def setUp(self):
        self.database_context = patched_postgres_database()
        self.database_context.__enter__()
        self.embedding_client = FakeEmbeddingClient()

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_upsert_document_stores_chunks(self):
        count = vector_store.upsert_document(
            "doc-agent",
            "agent tool memory",
            embedding_client=self.embedding_client,
            chunk_size=100,
            chunk_overlap=0,
        )

        chunks = vector_store.list_document_chunks("doc-agent")

        self.assertEqual(count, 1)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["id"], "doc-agent_chunk_0000")
        self.assertEqual(chunks[0]["text"], "agent tool memory")

    def test_upsert_document_replaces_old_chunks(self):
        vector_store.upsert_document(
            "doc-agent",
            "agent tool memory",
            embedding_client=self.embedding_client,
            chunk_size=100,
            chunk_overlap=0,
        )

        vector_store.upsert_document(
            "doc-agent",
            "vector database",
            embedding_client=self.embedding_client,
            chunk_size=100,
            chunk_overlap=0,
        )

        chunks = vector_store.list_document_chunks("doc-agent")

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "vector database")

    def test_search_returns_most_similar_chunks(self):
        vector_store.upsert_document(
            "doc-agent",
            "agent tool memory",
            embedding_client=self.embedding_client,
            chunk_size=100,
            chunk_overlap=0,
        )
        vector_store.upsert_document(
            "doc-food",
            "pork pork",
            embedding_client=self.embedding_client,
            chunk_size=100,
            chunk_overlap=0,
        )

        results = vector_store.search(
            "agent tool",
            top_k=1,
            embedding_client=self.embedding_client,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].document_id, "doc-agent")
        self.assertGreaterEqual(results[0].score, 0)

    def test_delete_document_removes_chunks(self):
        vector_store.upsert_document(
            "doc-agent",
            "agent tool memory",
            embedding_client=self.embedding_client,
            chunk_size=100,
            chunk_overlap=0,
        )

        vector_store.delete_document("doc-agent")

        self.assertEqual(vector_store.list_document_chunks("doc-agent"), [])

    def test_search_uses_chroma_backend_when_enabled(self):
        with patch.object(vector_store, "VECTOR_STORE_BACKEND", "chroma"):
            with patch.object(
                vector_store.langchain_chroma_store,
                "similarity_search",
                return_value=[
                    {
                        "score": 0.88,
                        "chunk_id": "doc-agent_chunk_0000",
                        "document_id": "doc-agent",
                        "chunk_index": 0,
                        "text": "agent tool memory",
                    }
                ],
            ) as search_mock:
                results = vector_store.search(
                    "agent tool",
                    top_k=1,
                    embedding_client=self.embedding_client,
                )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].document_id, "doc-agent")
        search_mock.assert_called_once_with("agent tool", 1, self.embedding_client)

    def test_upsert_document_indexes_chroma_when_enabled(self):
        with patch.object(vector_store, "VECTOR_STORE_BACKEND", "chroma"):
            with patch.object(
                vector_store.langchain_chroma_store,
                "replace_document_chunks",
            ) as replace_mock:
                count = vector_store.upsert_document(
                    "doc-agent",
                    "agent tool memory",
                    embedding_client=self.embedding_client,
                    chunk_size=100,
                    chunk_overlap=0,
                )

        self.assertEqual(count, 1)
        replace_mock.assert_called_once()
        self.assertEqual(replace_mock.call_args.args[0], "doc-agent")
        self.assertEqual(replace_mock.call_args.args[1], ["agent tool memory"])
        self.assertIs(replace_mock.call_args.args[2], self.embedding_client)

    def test_delete_document_deletes_chroma_chunks_when_enabled(self):
        vector_store.upsert_document(
            "doc-agent",
            "agent tool memory",
            embedding_client=self.embedding_client,
            chunk_size=100,
            chunk_overlap=0,
        )

        with patch.object(vector_store, "VECTOR_STORE_BACKEND", "chroma"):
            with patch.object(vector_store, "EmbeddingClient", return_value=self.embedding_client):
                with patch.object(
                    vector_store.langchain_chroma_store,
                    "delete_document_chunks",
                ) as delete_mock:
                    vector_store.delete_document("doc-agent")

        delete_mock.assert_called_once_with("doc-agent", self.embedding_client)
        self.assertEqual(vector_store.list_document_chunks("doc-agent"), [])

    def test_list_documents_groups_chunks_by_document(self):
        vector_store.upsert_document(
            "doc-agent",
            "agent tool memory",
            embedding_client=self.embedding_client,
            chunk_size=100,
            chunk_overlap=0,
        )
        vector_store.upsert_document_metadata("doc-agent", "project notes")

        documents = vector_store.list_documents()

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["document_id"], "doc-agent")
        self.assertEqual(documents[0]["chunk_count"], 1)
        self.assertEqual(documents[0]["notes"], "project notes")

    def test_find_document_by_content_hash_uses_metadata_fingerprint(self):
        vector_store.upsert_document(
            "doc-agent",
            "agent tool memory",
            embedding_client=self.embedding_client,
            chunk_size=100,
            chunk_overlap=0,
        )
        vector_store.upsert_document_metadata(
            "doc-agent",
            '{"fingerprint": {"content_hash": "hash-1"}}',
        )

        document_id = vector_store.find_document_by_content_hash("hash-1")

        self.assertEqual(document_id, "doc-agent")

    def test_list_duplicate_documents_by_content_hash_groups_matches(self):
        for document_id in ("doc-a", "doc-b", "doc-c"):
            vector_store.upsert_document(
                document_id,
                f"{document_id} text",
                embedding_client=self.embedding_client,
                chunk_size=100,
                chunk_overlap=0,
            )
        vector_store.upsert_document_metadata(
            "doc-a",
            '{"fingerprint": {"content_hash": "hash-1"}}',
        )
        vector_store.upsert_document_metadata(
            "doc-b",
            '{"fingerprint": {"content_hash": "hash-1"}}',
        )
        vector_store.upsert_document_metadata(
            "doc-c",
            '{"fingerprint": {"content_hash": "hash-2"}}',
        )

        duplicate_groups = vector_store.list_duplicate_documents_by_content_hash()

        self.assertEqual(len(duplicate_groups), 1)
        self.assertEqual(duplicate_groups[0]["content_hash"], "hash-1")
        self.assertEqual(
            [document["document_id"] for document in duplicate_groups[0]["documents"]],
            ["doc-a", "doc-b"],
        )

    def test_deduplicate_documents_removes_duplicates_and_reassigns(self):
        for document_id in ("doc-a", "doc-b"):
            vector_store.upsert_document(
                document_id,
                f"{document_id} text",
                embedding_client=self.embedding_client,
                chunk_size=100,
                chunk_overlap=0,
            )
            vector_store.upsert_document_metadata(
                document_id,
                '{"fingerprint": {"content_hash": "hash-1"}}',
            )
        reassign_calls = []

        result = vector_store.deduplicate_documents_by_content_hash(
            reassign_document=lambda from_id, to_id: reassign_calls.append((from_id, to_id)) or 2,
        )

        self.assertEqual(result["removed_count"], 1)
        self.assertEqual(result["removed_documents"][0]["document_id"], "doc-b")
        self.assertEqual(result["removed_documents"][0]["duplicate_of"], "doc-a")
        self.assertEqual(result["removed_documents"][0]["reassigned_source_files"], 2)
        self.assertEqual(reassign_calls, [("doc-b", "doc-a")])
        self.assertEqual(vector_store.list_document_chunks("doc-b"), [])
        self.assertEqual(len(vector_store.list_document_chunks("doc-a")), 1)

    def test_split_text_recursively_splits_long_paragraphs(self):
        text = (
            "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu "
            "nu xi omicron pi rho sigma tau upsilon phi chi psi omega"
        )

        chunks = vector_store.split_text(text, chunk_size=40, chunk_overlap=8)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 40 for chunk in chunks))
        self.assertTrue(any(chunks[index - 1][-4:] in chunks[index] for index in range(1, len(chunks))))

    def test_split_text_keeps_heading_on_each_section_chunk(self):
        text = (
            "# Deployment Guide\n\n"
            "Step one explains the environment preparation and dependency installation for the service. "
            "Step two explains how to start workers, verify health checks, and validate logs after deployment."
        )

        chunks = vector_store.split_text(text, chunk_size=70, chunk_overlap=10)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.startswith("# Deployment Guide") for chunk in chunks))

    def test_split_text_semantic_chunking_splits_on_topic_shift(self):
        text = (
            "agent tool memory agent tool memory agent tool memory agent tool memory. "
            "agent tool memory agent tool memory agent tool memory agent tool memory. "
            "weather pork weather pork weather pork weather pork weather pork weather pork. "
            "weather pork weather pork weather pork weather pork weather pork weather pork."
        )

        chunks = vector_store.split_text(
            text,
            chunk_size=220,
            chunk_overlap=0,
            embedding_client=self.embedding_client,
            enable_semantic_chunking=True,
        )

        self.assertEqual(len(chunks), 2)
        self.assertIn("agent tool memory", chunks[0])
        self.assertNotIn("weather pork", chunks[0])
        self.assertIn("weather pork", chunks[1])


class EmbeddingClientTests(unittest.TestCase):
    def tearDown(self):
        vector_store.clear_runtime_caches()

    def test_embed_splits_requests_into_supported_batch_size(self):
        client = vector_store.EmbeddingClient.__new__(vector_store.EmbeddingClient)
        client.model = "test-model"
        batch_sizes = []

        def create_embedding(model, input):
            batch_sizes.append(len(input))
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[float(index)])
                    for index, _ in enumerate(input)
                ],
            )

        client.client = SimpleNamespace(
            embeddings=SimpleNamespace(
                create=create_embedding,
            ),
        )

        embeddings = client.embed([f"text {index}" for index in range(25)])

        self.assertEqual(batch_sizes, [10, 10, 5])
        self.assertEqual(len(embeddings), 25)

    def test_embed_reuses_cached_embeddings_for_repeated_queries(self):
        client = vector_store.EmbeddingClient.__new__(vector_store.EmbeddingClient)
        client.model = "test-model"
        calls = []

        def create_embedding(model, input):
            calls.append(list(input))
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[float(len(text))]) for text in input],
            )

        client.client = SimpleNamespace(
            embeddings=SimpleNamespace(
                create=create_embedding,
            ),
        )

        first = client.embed(["same query"])
        second = client.embed(["same query"])

        self.assertEqual(first, second)
        self.assertEqual(calls, [["same query"]])


if __name__ == "__main__":
    unittest.main()
