import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import database
import main
import vector_store


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
_test_database_available = None


class FakeMilvusVectorClient:
    def __init__(self):
        self.vectors = {}

    def upsert_embeddings(self, items):
        for item in items:
            self.vectors[item["chunk_id"]] = item["embedding"]

    def delete_embeddings(self, chunk_ids):
        for chunk_id in chunk_ids:
            self.vectors.pop(chunk_id, None)

    def search(self, query_embedding, top_k):
        results = []
        for chunk_id, embedding in self.vectors.items():
            results.append({
                "chunk_id": chunk_id,
                "score": vector_store.cosine_similarity(query_embedding, embedding),
            })
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]


def require_test_database():
    global _test_database_available
    if not TEST_DATABASE_URL:
        raise unittest.SkipTest("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")
    if _test_database_available is False:
        raise unittest.SkipTest("TEST_DATABASE_URL is not reachable.")
    if _test_database_available is None:
        with patch.object(database, "DATABASE_URL", TEST_DATABASE_URL):
            with patch.object(database, "DATABASE_CONNECT_TIMEOUT_SECONDS", 1):
                try:
                    with database.connect() as connection:
                        connection.execute("SELECT 1").fetchone()
                except Exception as error:
                    _test_database_available = False
                    raise unittest.SkipTest(f"TEST_DATABASE_URL is not reachable: {error}")
        _test_database_available = True


def reset_test_database():
    require_test_database()
    database.init_db()
    with database.connect() as connection:
        connection.execute(
            """
            TRUNCATE TABLE
                admin_audit_events,
                knowledge_access_audit,
                bm25_posting,
                bm25_token,
                bm25_stats,
                knowledge_source_files,
                knowledge_sources,
                knowledge_index_jobs,
                vector_chunks,
                knowledge_documents,
                messages,
                conversations,
                sessions,
                departments,
                users
            RESTART IDENTITY CASCADE
            """
        )


@contextmanager
def patched_postgres_database(username="admin", password="password"):
    require_test_database()
    milvus_client = FakeMilvusVectorClient()
    patches = [
        patch.object(database, "DATABASE_URL", TEST_DATABASE_URL),
        patch.object(database, "APP_USERNAME", username),
        patch.object(database, "APP_PASSWORD", password),
        patch.object(main, "APP_USERNAME", username),
        patch.object(main, "APP_PASSWORD", password),
        patch.object(vector_store, "get_milvus_vector_client", return_value=milvus_client),
    ]
    started = []
    try:
        for patcher in patches:
            started.append(patcher.start())
        reset_test_database()
        database.init_db()
        vector_store.clear_runtime_caches()
        yield
    finally:
        vector_store.clear_runtime_caches()
        for patcher in reversed(patches):
            patcher.stop()
