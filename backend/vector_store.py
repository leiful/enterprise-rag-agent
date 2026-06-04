# -*- coding: utf-8 -*-

import hashlib
import json
import math
import re
from dataclasses import dataclass

from openai import OpenAI

import database
from config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL


DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 80
MAX_EMBEDDING_BATCH_SIZE = 10


@dataclass
class SearchResult:
    score: float
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str


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
        for start in range(0, len(texts), MAX_EMBEDDING_BATCH_SIZE):
            batch = texts[start:start + MAX_EMBEDDING_BATCH_SIZE]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            embeddings.extend(item.embedding for item in response.data)

        return embeddings


def split_text(text, chunk_size=DEFAULT_CHUNK_SIZE, chunk_overlap=DEFAULT_CHUNK_OVERLAP):
    """Split text on natural boundaries while keeping short notes together."""
    if not text.strip():
        return []

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

    segments = []
    for paragraph in paragraphs:
        if _is_heading(paragraph):
            segments.append({"text": paragraph, "is_title": True})
        elif len(paragraph) <= chunk_size:
            segments.append({"text": paragraph, "is_title": False})
        else:
            for sentence in _split_into_sentences(paragraph):
                segments.append({"text": sentence, "is_title": False})

    chunks = []
    current_chunk = []
    current_length = 0

    for segment in segments:
        seg_text = segment["text"]
        seg_len = len(seg_text)

        if segment["is_title"]:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(seg_text)
            current_length += seg_len
            continue

        if current_length + seg_len > chunk_size and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_length = 0

        current_chunk.append(seg_text)
        current_length += seg_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return [chunk for chunk in chunks if chunk.strip()]


def _is_heading(paragraph):
    lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
    if not lines:
        return False

    if lines[0].startswith("#"):
        return True

    return len(lines) == 1 and lines[0].endswith(":")


def _split_into_sentences(text):
    """Split long paragraphs into rough English and Chinese sentence units."""
    sentence_endings = re.compile(r'([。！？!?\.]+|[\n]{2,})')
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
    with database.connect() as connection:
        connection.execute(
            "DELETE FROM vector_chunks WHERE document_id = ?",
            (document_id,),
        )
        connection.execute(
            "DELETE FROM knowledge_documents WHERE document_id = ?",
            (document_id,),
        )


def upsert_document_metadata(document_id, notes=None):
    now = database.utc_now_iso()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_documents (document_id, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (document_id, notes, now, now),
        )


def upsert_document(
    document_id,
    text,
    embedding_client=None,
    chunk_size=DEFAULT_CHUNK_SIZE,
    chunk_overlap=DEFAULT_CHUNK_OVERLAP,
):
    chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    embedding_client = embedding_client or EmbeddingClient()

    embeddings = embedding_client.embed(chunks) if chunks else []
    now = database.utc_now_iso()

    with database.connect() as connection:
        connection.execute(
            "DELETE FROM vector_chunks WHERE document_id = ?",
            (document_id,),
        )

        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{document_id}_chunk_{index:04d}"
            connection.execute(
                """
                INSERT INTO vector_chunks (
                    id,
                    document_id,
                    chunk_index,
                    text,
                    embedding_json,
                    content_hash,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    document_id,
                    index,
                    chunk,
                    json.dumps(embedding),
                    content_hash(chunk),
                    now,
                    now,
                ),
            )

    return len(chunks)


def list_document_chunks(document_id):
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT id, document_id, chunk_index, text, content_hash, created_at, updated_at
            FROM vector_chunks
            WHERE document_id = ?
            ORDER BY chunk_index ASC
            """,
            (document_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def list_documents():
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                vector_chunks.document_id,
                knowledge_documents.notes,
                COUNT(*) AS chunk_count,
                MAX(vector_chunks.updated_at) AS updated_at
            FROM vector_chunks
            LEFT JOIN knowledge_documents
                ON knowledge_documents.document_id = vector_chunks.document_id
            GROUP BY vector_chunks.document_id
            ORDER BY updated_at DESC, vector_chunks.document_id ASC
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
    embedding_client = embedding_client or EmbeddingClient()
    query_embedding = embedding_client.embed([query])[0]

    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT id, document_id, chunk_index, text, embedding_json
            FROM vector_chunks
            """
        ).fetchall()

    results = []
    for row in rows:
        embedding = json.loads(row["embedding_json"])
        score = cosine_similarity(query_embedding, embedding)
        results.append(
            SearchResult(
                score=score,
                chunk_id=row["id"],
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                text=row["text"],
            )
        )

    results.sort(key=lambda result: result.score, reverse=True)
    return results[:top_k]


def tokenize(text):
    chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
    english_words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    numbers = re.findall(r'\b\d+\b', text)

    return chinese_chars + english_words + numbers


def bm25_search(query, top_k=10):
    query_tokens = tokenize(query)

    if not query_tokens:
        return []

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT id, document_id, chunk_index, text FROM vector_chunks"
        ).fetchall()

    scores = {}
    for row in rows:
        chunk_tokens = tokenize(row["text"])

        score = 0.0
        for token in query_tokens:
            count = chunk_tokens.count(token)
            if count > 0:
                score += count

        if score > 0:
            scores[row["id"]] = {
                "score": score,
                "row": row,
            }

    sorted_items = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
    results = []

    for item in sorted_items[:top_k]:
        row = item[1]["row"]
        results.append(
            SearchResult(
                score=item[1]["score"],
                chunk_id=row["id"],
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                text=row["text"],
            )
        )

    return results


def hybrid_search(query, top_k=3, bm25_weight=0.5, vector_weight=0.5):
    bm25_results = bm25_search(query, top_k=20)
    vector_results = search(query, top_k=20)

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

    max_bm25 = max([item["bm25_score"] for item in combined.values()] or [1])
    max_vector = max([item["vector_score"] for item in combined.values()] or [1])

    final_results = []
    for item in combined.values():
        normalized_bm25 = item["bm25_score"] / max_bm25 if max_bm25 > 0 else 0
        normalized_vector = item["vector_score"] / max_vector if max_vector > 0 else 0
        final_score = (normalized_bm25 * bm25_weight) + (normalized_vector * vector_weight)

        final_result = item["result"]
        final_result.score = final_score
        final_results.append(final_result)

    final_results.sort(key=lambda result: result.score, reverse=True)
    return final_results[:top_k]
