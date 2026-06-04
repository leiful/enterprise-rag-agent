import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import database
import vector_store


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
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_file = str(Path(self.temp_dir.name) / "test-agent.db")
        self.database_patch = patch.object(database, "DATABASE_FILE", self.database_file)
        self.database_patch.start()
        database.init_db()
        self.embedding_client = FakeEmbeddingClient()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

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
        self.assertGreater(results[0].score, 0)

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


class EmbeddingClientTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
