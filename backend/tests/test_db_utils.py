import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import database
import main
import vector_store


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
_test_database_available = None


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


def fake_vector_similarity_search(query, top_k, embedding_client):
    query_embedding = embedding_client.embed([query])[0]
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT id, document_id, chunk_index, text, embedding_json, metadata_json
            FROM vector_chunks
            """
        ).fetchall()

    results = []
    for row in rows:
        embedding = vector_store.json.loads(row["embedding_json"])
        results.append({
            "score": vector_store.cosine_similarity(query_embedding, embedding),
            "chunk_id": row["id"],
            "document_id": row["document_id"],
            "chunk_index": row["chunk_index"],
            "text": row["text"],
            "metadata": vector_store._parse_metadata_json(dict(row).get("metadata_json")),
        })
    results.sort(key=lambda result: result["score"], reverse=True)
    return results[:top_k]


@contextmanager
def patched_postgres_database(username="admin", password="password"):
    require_test_database()
    patches = [
        patch.object(database, "DATABASE_URL", TEST_DATABASE_URL),
        patch.object(database, "APP_USERNAME", username),
        patch.object(database, "APP_PASSWORD", password),
        patch.object(main, "APP_USERNAME", username),
        patch.object(main, "APP_PASSWORD", password),
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
