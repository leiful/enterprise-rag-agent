from __future__ import annotations
from typing import Any
from config import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR

_IMPORT_ERROR = None

try:
    from langchain_chroma import Chroma
    from langchain_core.documents import Document
    from langchain_core.embeddings import Embeddings
except ImportError as error:  # pragma: no cover - exercised only when deps are missing
    Chroma = None
    Document = None
    Embeddings = object
    _IMPORT_ERROR = error


_STORE_CACHE = {}


class OpenAICompatibleEmbeddings(Embeddings):
    """Bridge the existing embedding client into LangChain's embeddings interface."""

    def __init__(self, embedding_client):
        self.embedding_client = embedding_client

    def embed_documents(self, texts):
        return self.embedding_client.embed(list(texts))

    def embed_query(self, text):
        return self.embedding_client.embed([text])[0]


def ensure_langchain_chroma_available():
    if _IMPORT_ERROR is not None:
        raise RuntimeError(
            "LangChain/Chroma dependencies are not installed. "
            "Run `python -m pip install -r backend/requirements.txt` first."
        ) from _IMPORT_ERROR


def clear_store_cache():
    _STORE_CACHE.clear()


def _store_cache_key(model_name):
    return (
        str(CHROMA_PERSIST_DIR),
        CHROMA_COLLECTION_NAME,
        model_name or "",
    )


def get_store(embedding_client):
    ensure_langchain_chroma_available()
    model_name = getattr(embedding_client, "model", "")
    cache_key = _store_cache_key(model_name)
    store = _STORE_CACHE.get(cache_key)
    if store is None:
        CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        store = Chroma(
            collection_name=CHROMA_COLLECTION_NAME,
            persist_directory=str(CHROMA_PERSIST_DIR),
            embedding_function=OpenAICompatibleEmbeddings(embedding_client),
            collection_metadata={"hnsw:space": "cosine"},
        )
        _STORE_CACHE[cache_key] = store
    return store


def _existing_ids(store, document_id):
    payload = store.get(
        where={"document_id": document_id},
        include=[],
    )
    return payload.get("ids", []) if payload else []


def replace_document_chunks(document_id, chunks, embedding_client, chunk_metadatas=None):
    store = get_store(embedding_client)
    existing_ids = _existing_ids(store, document_id)
    if existing_ids:
        store.delete(ids=existing_ids)

    if not chunks:
        return

    chunk_metadatas = chunk_metadatas or [{} for _ in chunks]
    documents = []
    for index, chunk in enumerate(chunks):
        extra_metadata = chunk_metadatas[index] if index < len(chunk_metadatas) else {}
        metadata = {
            "document_id": document_id,
            "chunk_index": index,
            "chunk_id": f"{document_id}_chunk_{index:04d}",
        }
        metadata.update(extra_metadata or {})
        documents.append(
            Document(
                page_content=chunk,
                metadata=metadata,
            )
        )
    ids = [document.metadata["chunk_id"] for document in documents]
    store.add_documents(documents=documents, ids=ids)


def delete_document_chunks(document_id, embedding_client):
    store = get_store(embedding_client)
    existing_ids = _existing_ids(store, document_id)
    if existing_ids:
        store.delete(ids=existing_ids)


def similarity_search(query, top_k, embedding_client):
    store = get_store(embedding_client)
    matches = store.similarity_search_with_score(query, k=top_k)
    results = []
    for document, distance in matches:
        metadata = document.metadata or {}
        results.append(
            {
                "score": _distance_to_relevance(distance),
                "chunk_id": metadata.get("chunk_id", ""),
                "document_id": metadata.get("document_id", ""),
                "chunk_index": int(metadata.get("chunk_index", 0)),
                "metadata": dict(metadata),
                "text": document.page_content,
            }
        )
    return results


def _distance_to_relevance(distance: Any) -> float:
    try:
        numeric_distance = float(distance)
    except (TypeError, ValueError):
        return 0.0

    # Chroma returns a distance, so convert it into a "higher is better" score.
    return max(0.0, 1.0 - numeric_distance)
