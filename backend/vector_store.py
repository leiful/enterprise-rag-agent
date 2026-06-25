# -*- coding: utf-8 -*-

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from threading import Lock

from openai import OpenAI

import database
from app_logging import request_id_var
from config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    ENABLE_SEMANTIC_CHUNKING,
    QUERY_CACHE_MAX_ENTRIES,
    QUERY_CACHE_TTL_SECONDS,
    SEMANTIC_BOUNDARY_STD_FACTOR,
    SEMANTIC_CHUNK_MIN_UNITS,
    SEMANTIC_CHUNK_SOFT_RATIO,
    MILVUS_COLLECTION,
    MILVUS_TOKEN,
    MILVUS_URI,
)
from model_usage import record_model_usage


MAX_EMBEDDING_BATCH_SIZE = 10
MILVUS_METRIC_TYPE = "COSINE"
MILVUS_FIELD_CHUNK_ID = "chunk_id"
MILVUS_FIELD_EMBEDDING = "embedding"

# BM25 parameters
BM25_K1 = 1.5
BM25_B = 0.75
BM25_NORMALIZATION_K = 1.5

_CACHE_LOCK = Lock()
_EMBEDDING_CACHE = {}
_VECTOR_SEARCH_CACHE = {}
_BM25_SEARCH_CACHE = {}
_HYBRID_SEARCH_CACHE = {}
_METADATA_CACHE = {}
_MILVUS_VECTOR_CLIENT = None


@dataclass
class SearchResult:
    score: float
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    metadata: dict = field(default_factory=dict)



def _cache_get(cache, key):
    now = time.time()
    with _CACHE_LOCK:
        item = cache.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at <= now:
            cache.pop(key, None)
            return None
        return value


def _cache_set(cache, key, value):
    expires_at = time.time() + QUERY_CACHE_TTL_SECONDS
    with _CACHE_LOCK:
        if len(cache) >= QUERY_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(cache))
            cache.pop(oldest_key, None)
        cache[key] = (expires_at, value)


def clear_runtime_caches(reset_milvus_client=False):
    global _MILVUS_VECTOR_CLIENT
    with _CACHE_LOCK:
        _EMBEDDING_CACHE.clear()
        _VECTOR_SEARCH_CACHE.clear()
        _BM25_SEARCH_CACHE.clear()
        _HYBRID_SEARCH_CACHE.clear()
        _METADATA_CACHE.clear()
    if reset_milvus_client:
        _MILVUS_VECTOR_CLIENT = None


def _clone_results(results):
    return [
        SearchResult(
            score=result.score,
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            chunk_index=result.chunk_index,
            text=result.text,
            metadata=dict(result.metadata or {}),
        )
        for result in results
    ]


class EmbeddingClient:
    def __init__(
        self,
        api_key=EMBEDDING_API_KEY,
        base_url=EMBEDDING_BASE_URL,
        model=EMBEDDING_MODEL,
    ):
        if not api_key:
            raise ValueError("Missing EMBEDDING_API_KEY. Set it in .env.")

        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def embed(self, texts):
        embeddings = []
        missing_indices = []
        missing_texts = []

        for index, text in enumerate(texts):
            cache_key = (self.model, text)
            cached_embedding = _cache_get(_EMBEDDING_CACHE, cache_key)
            if cached_embedding is None:
                embeddings.append(None)
                missing_indices.append(index)
                missing_texts.append(text)
            else:
                embeddings.append(cached_embedding)

        for start in range(0, len(missing_texts), MAX_EMBEDDING_BATCH_SIZE):
            batch = missing_texts[start : start + MAX_EMBEDDING_BATCH_SIZE]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            record_model_usage(
                provider="dashscope",
                model=self.model,
                operation="embedding",
                request_id=request_id_var.get(),
                input_texts=batch,
                document_count=len(batch),
            )
            batch_embeddings = [item.embedding for item in response.data]
            for offset, embedding in enumerate(batch_embeddings):
                original_index = missing_indices[start + offset]
                embeddings[original_index] = embedding
                _cache_set(_EMBEDDING_CACHE, (self.model, texts[original_index]), embedding)

        return embeddings


class MilvusVectorClient:
    def __init__(
        self,
        uri=MILVUS_URI,
        token=MILVUS_TOKEN,
        collection_name=MILVUS_COLLECTION,
        dimension=EMBEDDING_DIM,
    ):
        if not uri:
            raise ValueError("Missing MILVUS_URI. Set it in .env.")
        if not collection_name:
            raise ValueError("Missing MILVUS_COLLECTION. Set it in .env.")

        try:
            from pymilvus import MilvusClient
        except ImportError as error:
            raise RuntimeError("pymilvus is required for Milvus vector search.") from error

        self.collection_name = collection_name
        self.dimension = dimension
        kwargs = {"uri": uri}
        if token:
            kwargs["token"] = token
        self.client = MilvusClient(**kwargs)
        self._ensure_collection()

    def _ensure_collection(self):
        if self.client.has_collection(self.collection_name):
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            dimension=self.dimension,
            primary_field_name=MILVUS_FIELD_CHUNK_ID,
            id_type="string",
            max_length=512,
            vector_field_name=MILVUS_FIELD_EMBEDDING,
            metric_type=MILVUS_METRIC_TYPE,
            auto_id=False,
        )

    def upsert_embeddings(self, items):
        if not items:
            return
        self.client.upsert(
            collection_name=self.collection_name,
            data=[
                {
                    MILVUS_FIELD_CHUNK_ID: item["chunk_id"],
                    MILVUS_FIELD_EMBEDDING: item["embedding"],
                }
                for item in items
            ],
        )

    def delete_embeddings(self, chunk_ids):
        if not chunk_ids:
            return
        self.client.delete(
            collection_name=self.collection_name,
            ids=list(chunk_ids),
        )

    def search(self, query_embedding, top_k):
        if top_k <= 0:
            return []
        result_sets = self.client.search(
            collection_name=self.collection_name,
            data=[query_embedding],
            limit=top_k,
            output_fields=[MILVUS_FIELD_CHUNK_ID],
            search_params={"metric_type": MILVUS_METRIC_TYPE},
        )
        if not result_sets:
            return []
        results = []
        for item in result_sets[0]:
            chunk_id = None
            if isinstance(item, dict):
                chunk_id = item.get(MILVUS_FIELD_CHUNK_ID) or item.get("id")
                entity = item.get("entity") or {}
                chunk_id = entity.get(MILVUS_FIELD_CHUNK_ID, chunk_id)
                score = item.get("distance", item.get("score", 0.0))
            else:
                entity = getattr(item, "entity", {}) or {}
                if hasattr(entity, "get"):
                    chunk_id = entity.get(MILVUS_FIELD_CHUNK_ID)
                chunk_id = chunk_id or getattr(item, "id", None)
                score = getattr(item, "distance", getattr(item, "score", 0.0))
            if chunk_id:
                results.append({"chunk_id": str(chunk_id), "score": float(score or 0.0)})
        return results


def get_milvus_vector_client():
    global _MILVUS_VECTOR_CLIENT
    if _MILVUS_VECTOR_CLIENT is None:
        _MILVUS_VECTOR_CLIENT = MilvusVectorClient()
    return _MILVUS_VECTOR_CLIENT


def tokenize(text):
    """Tokenize Chinese characters/ngrams, English words, and numbers."""
    tokens = []

    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    tokens.extend(chinese_chars)

    chinese_seqs = re.findall(r'[\u4e00-\u9fff]+', text)
    for seq in chinese_seqs:
        if len(seq) >= 2:
            for i in range(len(seq) - 1):
                tokens.append(seq[i:i+2])
        if len(seq) >= 3:
            for i in range(len(seq) - 2):
                tokens.append(seq[i:i+3])

    english_words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
    tokens.extend(english_words)

    numbers = re.findall(r'\b\d{2,}\b', text)
    tokens.extend(numbers)

    return tokens



def split_text(
    text,
    chunk_size=DEFAULT_CHUNK_SIZE,
    chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    embedding_client=None,
    enable_semantic_chunking=None,
):
    """标题优先，章节内部使用递归字符分割，并应用字符 overlap。"""
    if not text.strip():
        return []

    if enable_semantic_chunking is None:
        enable_semantic_chunking = ENABLE_SEMANTIC_CHUNKING

    paragraphs = []
    current_paragraph = []

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            current_paragraph.append(line)
        elif current_paragraph:
            paragraph = "\n".join(current_paragraph).strip()
            if paragraph:
                paragraphs.append(paragraph)
            current_paragraph = []

    if current_paragraph:
        paragraph = "\n".join(current_paragraph).strip()
        if paragraph:
            paragraphs.append(paragraph)

    sections = []
    current_section = {"title": None, "paragraphs": []}
    for paragraph in paragraphs:
        if _is_heading(paragraph):
            if current_section["title"] or current_section["paragraphs"]:
                sections.append(current_section)
            current_section = {"title": paragraph, "paragraphs": []}
        else:
            current_section["paragraphs"].append(paragraph)

    if current_section["title"] or current_section["paragraphs"]:
        sections.append(current_section)

    chunks = []
    for section in sections:
        title = section["title"]
        body = "\n\n".join(section["paragraphs"]).strip()

        if title and not body:
            chunks.append(title)
            continue

        if title:
            title_prefix = f"{title}\n\n"
            available_size = max(1, chunk_size - len(title_prefix))
            body_chunks = _split_section_body(
                body,
                available_size,
                chunk_overlap,
                embedding_client=embedding_client,
                enable_semantic_chunking=enable_semantic_chunking,
            )
            chunks.extend(
                f"{title_prefix}{body_chunk}".strip()
                for body_chunk in body_chunks
                if body_chunk.strip()
            )
        else:
            chunks.extend(
                _split_section_body(
                    body,
                    chunk_size,
                    chunk_overlap,
                    embedding_client=embedding_client,
                    enable_semantic_chunking=enable_semantic_chunking,
                )
            )

    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def split_segments(segments, chunk_size=DEFAULT_CHUNK_SIZE, chunk_overlap=DEFAULT_CHUNK_OVERLAP, embedding_client=None):
    chunks = []
    chunk_metadatas = []
    for segment in segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        segment_metadata = dict(segment.get("metadata") or {})
        segment_chunks = split_text(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            embedding_client=embedding_client,
        )
        for chunk in segment_chunks:
            chunks.append(chunk)
            chunk_metadatas.append(dict(segment_metadata))
    return chunks, chunk_metadatas


def _is_heading(paragraph):
    lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
    if not lines:
        return False

    if lines[0].startswith("#"):
        return True

    return len(lines) == 1 and lines[0].endswith(":")


def _split_into_sentences(text):
    """Split long paragraphs into rough English and Chinese sentence units."""
    sentence_endings = re.compile(r'([\u3002\uff01\uff1f!?\.]+|[\n]{2,})')
    parts = sentence_endings.split(text)

    sentences = []
    for i in range(0, len(parts), 2):
        if i + 1 < len(parts):
            sentence = parts[i].strip() + parts[i + 1].strip()
        else:
            sentence = parts[i].strip()
        if sentence:
            sentences.append(sentence)

    return sentences


def _split_with_separator(text, separator):
    if not separator:
        return [text]

    parts = text.split(separator)
    segments = []
    for index, part in enumerate(parts):
        stripped = part.strip()
        if not stripped:
            continue
        if index < len(parts) - 1:
            segments.append(f"{stripped}{separator}".strip())
        else:
            segments.append(stripped)

    return segments


def _character_overlap(text, overlap_size):
    if overlap_size <= 0:
        return ""

    overlap_text = text[-overlap_size:].strip()
    if not overlap_text:
        return ""

    for separator in ("\n\n", "\n", " "):
        if separator in overlap_text:
            overlap_text = overlap_text.split(separator, 1)[-1].strip()
    return overlap_text


def _split_section_body(text, chunk_size, chunk_overlap, embedding_client=None, enable_semantic_chunking=False):
    if not text.strip():
        return []

    if (
        enable_semantic_chunking
        and embedding_client is not None
        and len(text) >= chunk_size
    ):
        semantic_chunks = _semantic_split_text(text, chunk_size, chunk_overlap, embedding_client)
        if semantic_chunks:
            return semantic_chunks

    return _recursive_split_text(text, chunk_size, chunk_overlap)


def _merge_split_segments(parts, chunk_size, chunk_overlap, separator):
    chunks = []
    current = ""

    for part in parts:
        candidate = part if not current else f"{current}{separator}{part}".strip()
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current.strip())

        overlap_prefix = _character_overlap(chunks[-1], chunk_overlap) if chunks else ""
        if overlap_prefix:
            allowed_overlap = max(0, chunk_size - len(part) - len(separator))
            overlap_prefix = overlap_prefix[-allowed_overlap:] if allowed_overlap else ""

        current = f"{overlap_prefix}{separator}{part}".strip() if overlap_prefix else part
        if len(current) > chunk_size:
            current = part

    if current:
        chunks.append(current.strip())

    return chunks


def _split_into_semantic_units(text):
    units = []
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text) if paragraph.strip()]
    for paragraph in paragraphs:
        sentences = _split_into_sentences(paragraph)
        if len(sentences) >= 2:
            units.extend(sentence.strip() for sentence in sentences if sentence.strip())
        else:
            units.append(paragraph)

    return [unit for unit in units if unit]


def _join_semantic_units(units):
    return "\n".join(unit.strip() for unit in units if unit and unit.strip()).strip()


def _semantic_similarity_threshold(similarities):
    if not similarities:
        return None

    mean_similarity = sum(similarities) / len(similarities)
    variance = sum((value - mean_similarity) ** 2 for value in similarities) / len(similarities)
    std_similarity = math.sqrt(variance)
    threshold = mean_similarity - (SEMANTIC_BOUNDARY_STD_FACTOR * std_similarity)
    return max(-1.0, min(1.0, threshold))


def _collect_overlap_units(units, overlap_size):
    if overlap_size <= 0 or not units:
        return []

    overlap_units = []
    current_length = 0
    for unit in reversed(units):
        overlap_units.insert(0, unit)
        current_length += len(unit) + 1
        if current_length >= overlap_size:
            break

    return overlap_units


def _semantic_split_text(text, chunk_size, chunk_overlap, embedding_client):
    units = _split_into_semantic_units(text)
    if len(units) < SEMANTIC_CHUNK_MIN_UNITS:
        return []

    try:
        embeddings = embedding_client.embed(units)
    except Exception:
        return []

    similarities = [
        cosine_similarity(embeddings[index], embeddings[index + 1])
        for index in range(len(embeddings) - 1)
    ]
    threshold = _semantic_similarity_threshold(similarities)
    soft_limit = max(1, min(chunk_size, int(chunk_size * SEMANTIC_CHUNK_SOFT_RATIO)))

    chunks = []
    current_units = []

    for index, unit in enumerate(units):
        current_units.append(unit)
        current_text = _join_semantic_units(current_units)
        current_length = len(current_text)
        next_similarity = similarities[index] if index < len(similarities) else None

        should_cut = False
        if current_length >= chunk_size:
            should_cut = True
        elif (
            current_length >= soft_limit
            and threshold is not None
            and next_similarity is not None
            and next_similarity < threshold
        ):
            should_cut = True

        if should_cut:
            chunks.append(current_text)
            current_units = _collect_overlap_units(current_units, chunk_overlap)

    trailing_text = _join_semantic_units(current_units)
    if trailing_text:
        chunks.append(trailing_text)

    normalized_chunks = []
    seen = set()
    for chunk in chunks:
        if not chunk or chunk in seen:
            continue
        seen.add(chunk)
        if len(chunk) <= chunk_size:
            normalized_chunks.append(chunk)
        else:
            normalized_chunks.extend(_recursive_split_text(chunk, chunk_size, chunk_overlap))

    return normalized_chunks


def _recursive_split_text(text, chunk_size, chunk_overlap, separators=None):
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    separators = separators or ["\n\n", "\n", "\u3002", "\uff01", "\uff1f", ". ", "! ", "? ", "\uff1b", "; ", "\uff0c", ", ", " "]

    if not separators:
        step = max(1, chunk_size - chunk_overlap)
        return [
            text[start:start + chunk_size].strip()
            for start in range(0, len(text), step)
            if text[start:start + chunk_size].strip()
        ]

    separator = next((item for item in separators if item and item in text), None)
    if separator is None:
        step = max(1, chunk_size - chunk_overlap)
        return [
            text[start:start + chunk_size].strip()
            for start in range(0, len(text), step)
            if text[start:start + chunk_size].strip()
        ]

    parts = _split_with_separator(text, separator)
    split_parts = []
    next_separators = separators[separators.index(separator) + 1:]
    for part in parts:
        if len(part) <= chunk_size:
            split_parts.append(part)
        else:
            split_parts.extend(_recursive_split_text(part, chunk_size, chunk_overlap, next_separators))

    return _merge_split_segments(split_parts, chunk_size, chunk_overlap, separator if separator != " " else " ")


def _get_overlap_segment(text, overlap_size):
    if overlap_size <= 0 or not text:
        return []

    words = text.split()
    if len(words) <= 3:
        return words

    overlap_words = []
    current_length = 0
    for word in reversed(words):
        overlap_words.insert(0, word)
        current_length += len(word) + 1
        if current_length >= overlap_size:
            break

    return overlap_words


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_metadata_json(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def cosine_similarity(vector_a, vector_b):
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
    length_a = math.sqrt(sum(a * a for a in vector_a))
    length_b = math.sqrt(sum(b * b for b in vector_b))

    if length_a == 0 or length_b == 0:
        return 0.0

    return dot_product / (length_a * length_b)


def init_vector_store():
    database.init_db()


def delete_document(document_id):
    chunk_ids = []
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT id FROM vector_chunks WHERE document_id = %s",
            (document_id,)
        ).fetchall()
        chunk_ids = [row["id"] for row in rows]

    for chunk_id in chunk_ids:
        database.delete_bm25_for_chunk(chunk_id)
    if chunk_ids:
        get_milvus_vector_client().delete_embeddings(chunk_ids)

    with database.connect() as connection:
        connection.execute(
            "DELETE FROM vector_chunks WHERE document_id = %s",
            (document_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_documents WHERE document_id = %s",
            (document_id,),
        )

    database.update_bm25_stats()
    clear_runtime_caches()



def upsert_document_metadata(document_id, notes=None):
    now = database.utc_now_iso()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_documents (document_id, notes, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                notes = EXCLUDED.notes,
                updated_at = EXCLUDED.updated_at
            """,
            (document_id, notes, now, now),
        )
    with _CACHE_LOCK:
        _METADATA_CACHE.pop(document_id, None)


def upsert_document(
    document_id,
    text,
    embedding_client=None,
    chunk_size=DEFAULT_CHUNK_SIZE,
    chunk_overlap=DEFAULT_CHUNK_OVERLAP,
):
    return upsert_document_segments(
        document_id,
        [{"text": text, "metadata": {}}],
        embedding_client=embedding_client,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def upsert_document_segments(
    document_id,
    segments,
    embedding_client=None,
    chunk_size=DEFAULT_CHUNK_SIZE,
    chunk_overlap=DEFAULT_CHUNK_OVERLAP,
):
    embedding_client = embedding_client or EmbeddingClient()
    chunks, chunk_metadatas = split_segments(
        segments,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embedding_client=embedding_client,
    )

    embeddings = embedding_client.embed(chunks) if chunks else []
    now = database.utc_now_iso()

    old_chunk_ids = []
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT id FROM vector_chunks WHERE document_id = %s",
            (document_id,),
        ).fetchall()
        old_chunk_ids = [row["id"] for row in rows]
    
    for chunk_id in old_chunk_ids:
        database.delete_bm25_for_chunk(chunk_id)
    if old_chunk_ids:
        get_milvus_vector_client().delete_embeddings(old_chunk_ids)

    milvus_items = []
    
    with database.connect() as connection:
        connection.execute(
            "DELETE FROM vector_chunks WHERE document_id = %s",
            (document_id,),
        )

        for index, chunk in enumerate(chunks):
            chunk_id = f"{document_id}_chunk_{index:04d}"
            chunk_metadata = chunk_metadatas[index] if index < len(chunk_metadatas) else {}
            
            tokens = tokenize(chunk)
            token_count = len(tokens)
            
            embedding = embeddings[index] if index < len(embeddings) else []
            connection.execute(
                """
                INSERT INTO vector_chunks (
                    id,
                    document_id,
                    chunk_index,
                    text,
                    metadata_json,
                    content_hash,
                    token_count,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    chunk_id,
                    document_id,
                    index,
                    chunk,
                    json.dumps(chunk_metadata, ensure_ascii=False),
                    content_hash(chunk),
                    token_count,
                    now,
                    now,
                ),
            )
            
            database.add_bm25_for_chunk(chunk_id, tokens, connection=connection)
            milvus_items.append({
                "chunk_id": chunk_id,
                "embedding": embedding,
            })

    get_milvus_vector_client().upsert_embeddings(milvus_items)
    database.update_bm25_stats()
    clear_runtime_caches()

    return len(chunks)


def list_document_chunks(document_id):
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT id, document_id, chunk_index, text, metadata_json, content_hash, created_at, updated_at
            FROM vector_chunks
            WHERE document_id = %s
            ORDER BY chunk_index ASC
            """,
            (document_id,),
        ).fetchall()

    chunks = []
    for row in rows:
        item = dict(row)
        item["metadata"] = _parse_metadata_json(item.pop("metadata_json", None))
        chunks.append(item)
    return chunks


def list_documents():
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                vc.document_id,
                kd.notes,
                COUNT(*) AS chunk_count,
                MAX(vc.updated_at) AS updated_at
            FROM vector_chunks vc
            LEFT JOIN knowledge_documents kd
                ON kd.document_id = vc.document_id
            GROUP BY vc.document_id, kd.notes
            ORDER BY updated_at DESC, vc.document_id ASC
            """
        ).fetchall()

    return [_format_document_row(row) for row in rows]


def _format_document_row(row):
    document = dict(row)
    notes = document.get("notes")

    if notes:
        try:
            metadata = json.loads(notes)
        except json.JSONDecodeError:
            metadata = None

        if isinstance(metadata, dict) and "user_notes" in metadata:
            document["notes"] = metadata["user_notes"]

    return document


def search(query, top_k=3, embedding_client=None):
    cache_key = (query, top_k, EMBEDDING_MODEL)
    cached_results = _cache_get(_VECTOR_SEARCH_CACHE, cache_key)
    if cached_results is not None:
        return _clone_results(cached_results)

    embedding_client = embedding_client or EmbeddingClient()
    query_embedding = embedding_client.embed([query])[0]
    vector_hits = get_milvus_vector_client().search(query_embedding, top_k)
    if not vector_hits:
        return []

    chunk_ids = [hit["chunk_id"] for hit in vector_hits if hit.get("chunk_id")]
    if not chunk_ids:
        return []

    with database.connect() as connection:
        placeholders = ",".join("%s" for _ in chunk_ids)
        rows = connection.execute(
            f"""
            SELECT id, document_id, chunk_index, text, metadata_json
            FROM vector_chunks
            WHERE id IN ({placeholders})
            """,
            chunk_ids,
        ).fetchall()

    rows_by_id = {row["id"]: row for row in rows}
    top_results = []
    for hit in vector_hits:
        row = rows_by_id.get(hit.get("chunk_id"))
        if not row:
            continue
        top_results.append(
            SearchResult(
                score=hit.get("score", 0.0),
                chunk_id=row["id"],
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                text=row["text"],
                metadata=_parse_metadata_json(row.get("metadata_json")),
            )
        )

    _cache_set(_VECTOR_SEARCH_CACHE, cache_key, _clone_results(top_results))
    return top_results


def compute_bm25_score(query_tokens, chunk_postings, doc_len, avg_doc_len, total_docs):
    """
    计算 BM25 分数
    
    BM25 公式：
    score = sum( IDF(qi) * (f(qi, D) * (k1 + 1)) / (f(qi, D) + k1 * (1 - b + b * (|D| / avgdl)) )
    """
    score = 0.0
    
    token_info = {p["token"]: (p["tf"], p["doc_freq"]) for p in chunk_postings}
    for token in query_tokens:
        if token not in token_info:
            continue
        
        tf, doc_freq = token_info[token]
        
        idf = math.log( ( (total_docs - doc_freq + 0.5) / (doc_freq + 0.5) ) + 1 )
        
        numerator = tf * (BM25_K1 + 1)
        denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * (doc_len / avg_doc_len if avg_doc_len > 0 else 1))
        
        score += idf * (numerator / denominator)
    
    return score


def bm25_search(query, top_k=10):
    """真正的 BM25 搜索实现"""
    cache_key = (query, top_k)
    cached_results = _cache_get(_BM25_SEARCH_CACHE, cache_key)
    if cached_results is not None:
        return _clone_results(cached_results)

    query_tokens = tokenize(query)

    if not query_tokens:
        return []

    stats = database.get_bm25_stats()
    total_docs = stats["total_docs"]
    avg_doc_len = stats["avg_doc_len"]
    
    if total_docs == 0:
        return []

    postings_by_chunk = database.search_bm25_postings(query_tokens)
    
    if not postings_by_chunk:
        return []

    chunk_ids = list(postings_by_chunk.keys())
    token_counts = database.get_chunk_token_counts(chunk_ids)

    results = []
    with database.connect() as connection:
        placeholders = ",".join("%s" for _ in chunk_ids)
        rows = connection.execute(
            f"""
            SELECT id, document_id, chunk_index, text, metadata_json
            FROM vector_chunks 
            WHERE id IN ({placeholders})
            """,
            chunk_ids
        ).fetchall()
        
        chunk_info = {row["id"]: row for row in rows}

    scores = []
    for chunk_id, postings in postings_by_chunk.items():
        if chunk_id not in chunk_info:
            continue
        
        doc_len = token_counts.get(chunk_id, 0)
        bm25_score = compute_bm25_score(
            query_tokens, 
            postings, 
            doc_len, 
            avg_doc_len, 
            total_docs
        )
        
        if bm25_score > 0:
            row = chunk_info[chunk_id]
            row_data = dict(row)
            scores.append({
                "score": bm25_score,
                "chunk_id": chunk_id,
                "document_id": row["document_id"],
                "chunk_index": row["chunk_index"],
                "text": row["text"],
                "metadata": _parse_metadata_json(row_data.get("metadata_json")),
            })

    scores.sort(key=lambda x: x["score"], reverse=True)
    
    scores.sort(key=lambda x: x["score"], reverse=True)

    results = []
    for item in scores[:top_k]:
        results.append(
            SearchResult(
                score=item["score"],
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                chunk_index=item["chunk_index"],
                text=item["text"],
                metadata=item.get("metadata", {}),
            )
        )

    _cache_set(_BM25_SEARCH_CACHE, cache_key, _clone_results(results))
    return results


def _bounded_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _normalized_bm25_score(score):
    if score <= 0:
        return 0.0
    return score / (score + BM25_NORMALIZATION_K)


def _who_query_subject(query):
    compact = re.sub(r"[\s,，。.!！?？:：;；、]+", "", query or "")
    if compact.startswith("谁是") and len(compact) > 2:
        subject = compact[2:]
    elif compact.endswith("是谁") and len(compact) > 2:
        subject = compact[:-2]
    else:
        return None

    if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·]{2,12}", subject):
        return subject
    return None


def hybrid_search(query, top_k=3, bm25_weight=0.5, vector_weight=0.5):
    cache_key = (query, top_k, bm25_weight, vector_weight)
    cached_results = _cache_get(_HYBRID_SEARCH_CACHE, cache_key)
    if cached_results is not None:
        return _clone_results(cached_results)

    bm25_results = bm25_search(query, top_k=top_k)
    vector_results = search(query, top_k=top_k)

    combined = {}

    for result in bm25_results:
        key = result.chunk_id
        if key not in combined:
            combined[key] = {
                "result": result,
                "bm25_score": result.score,
                "vector_score": 0.0,
            }
        else:
            combined[key]["bm25_score"] = result.score

    for result in vector_results:
        key = result.chunk_id
        if key not in combined:
            combined[key] = {
                "result": result,
                "bm25_score": 0.0,
                "vector_score": result.score,
            }
        else:
            combined[key]["vector_score"] = result.score

    who_subject = _who_query_subject(query)

    final_results = []
    for item in combined.values():
        normalized_bm25 = _normalized_bm25_score(item["bm25_score"])
        normalized_vector = _bounded_score(item["vector_score"])
        final_score = (normalized_bm25 * bm25_weight) + (normalized_vector * vector_weight)

        final_result = item["result"]
        if who_subject:
            searchable_text = f"{final_result.document_id}\n{final_result.text}".lower()
            if who_subject.lower() not in searchable_text:
                final_score = min(final_score, 0.15)
        final_result.score = final_score
        final_results.append(final_result)

    final_results.sort(key=lambda result: result.score, reverse=True)
    top_results = final_results[:top_k]
    _cache_set(_HYBRID_SEARCH_CACHE, cache_key, _clone_results(top_results))
    return top_results


def get_document_metadata(document_id):
    """获取文档元数据"""
    cached_metadata = _cache_get(_METADATA_CACHE, document_id)
    if cached_metadata is not None:
        return cached_metadata

    with database.connect() as connection:
        row = connection.execute(
            "SELECT notes FROM knowledge_documents WHERE document_id = %s",
            (document_id,)
        ).fetchone()
        
        if row and row["notes"]:
            try:
                import json
                metadata = json.loads(row["notes"])
                _cache_set(_METADATA_CACHE, document_id, metadata)
                return metadata
            except Exception:
                pass
        return None


def find_document_by_content_hash(content_hash_value, exclude_document_id=None):
    if not content_hash_value:
        return None

    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT document_id, notes
            FROM knowledge_documents
            WHERE notes IS NOT NULL
            ORDER BY updated_at ASC, document_id ASC
            """
        ).fetchall()

    for row in rows:
        document_id = row["document_id"]
        if exclude_document_id and document_id == exclude_document_id:
            continue
        try:
            metadata = json.loads(row["notes"])
        except Exception:
            continue
        fingerprint = metadata.get("fingerprint") if isinstance(metadata, dict) else None
        if isinstance(fingerprint, dict) and fingerprint.get("content_hash") == content_hash_value:
            return document_id
    return None


def list_duplicate_documents_by_content_hash():
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT document_id, notes, created_at, updated_at
            FROM knowledge_documents
            WHERE notes IS NOT NULL
            ORDER BY updated_at ASC, created_at ASC, document_id ASC
            """
        ).fetchall()

    grouped = {}
    for row in rows:
        try:
            metadata = json.loads(row["notes"])
        except Exception:
            continue
        fingerprint = metadata.get("fingerprint") if isinstance(metadata, dict) else None
        content_hash_value = fingerprint.get("content_hash") if isinstance(fingerprint, dict) else None
        if not content_hash_value:
            continue
        grouped.setdefault(content_hash_value, []).append(dict(row))

    return [
        {
            "content_hash": content_hash_value,
            "documents": documents,
        }
        for content_hash_value, documents in grouped.items()
        if len(documents) > 1
    ]


def deduplicate_documents_by_content_hash(reassign_document=None):
    duplicate_groups = list_duplicate_documents_by_content_hash()
    removed_documents = []
    for group in duplicate_groups:
        documents = group["documents"]
        keep_document_id = documents[0]["document_id"]
        for duplicate in documents[1:]:
            duplicate_document_id = duplicate["document_id"]
            reassigned_source_files = 0
            if reassign_document:
                reassigned_source_files = reassign_document(duplicate_document_id, keep_document_id)
            delete_document(duplicate_document_id)
            removed_documents.append({
                "document_id": duplicate_document_id,
                "duplicate_of": keep_document_id,
                "content_hash": group["content_hash"],
                "reassigned_source_files": reassigned_source_files,
            })

    if removed_documents:
        clear_runtime_caches()

    return {
        "duplicate_group_count": len(duplicate_groups),
        "removed_count": len(removed_documents),
        "removed_documents": removed_documents,
    }


def rebuild_bm25_index():
    """
    为所有已存在的文档重建 BM25 索引
    用于在系统升级后为旧数据建立索引
    """
    with database.connect() as connection:
        connection.execute("DELETE FROM bm25_posting")
        connection.execute("DELETE FROM bm25_token")
        connection.execute("DELETE FROM bm25_stats")
    
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT id, document_id, text FROM vector_chunks"
        ).fetchall()
    
    for row in rows:
        chunk_id = row["id"]
        text = row["text"]
        
        # Tokenize
        tokens = tokenize(text)
        token_count = len(tokens)
        
        with database.connect() as connection:
            connection.execute(
                "UPDATE vector_chunks SET token_count = %s WHERE id = %s",
                (token_count, chunk_id)
            )
        
        database.add_bm25_for_chunk(chunk_id, tokens)
    
    database.update_bm25_stats()
    clear_runtime_caches()
    
    return len(rows)
