import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import database
import main
import vector_store


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


def require_test_database():
    if not TEST_DATABASE_URL:
        raise unittest.SkipTest("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")


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
                users
            RESTART IDENTITY CASCADE
            """
        )


def fake_chroma_similarity_search(query, top_k, embedding_client):
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
        patch.object(vector_store, "VECTOR_STORE_BACKEND", "chroma"),
        patch.object(vector_store.langchain_chroma_store, "replace_document_chunks"),
        patch.object(vector_store.langchain_chroma_store, "delete_document_chunks"),
        patch.object(
            vector_store.langchain_chroma_store,
            "similarity_search",
            side_effect=fake_chroma_similarity_search,
        ),
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
