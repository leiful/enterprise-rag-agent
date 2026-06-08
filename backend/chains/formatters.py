# -*- coding: utf-8 -*-

from config import MIN_EVIDENCE_SOURCES


SOURCE_METADATA_KEYS = (
    "file_name",
    "source_path",
    "category",
    "tags",
    "department",
    "doc_type",
    "sensitivity",
    "version",
    "owner",
    "effective_date",
    "expiry_date",
    "section_path",
    "section_title",
    "sheet_name",
    "row_start",
    "row_end",
)


def _format_source_metadata(metadata):
    if not isinstance(metadata, dict):
        return ""

    parts = []
    for key in SOURCE_METADATA_KEYS:
        value = metadata.get(key)
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = ",".join(str(item) for item in value if str(item).strip())
        parts.append(f"{key}={value}")

    return f" {' '.join(parts)}" if parts else ""


def format_knowledge_preflight_payload(payload, *, knowledge_preflight_prefix):
    user_input = payload["user_input"]
    query_to_search = payload["query_to_search"]
    min_score = payload["min_score"]
    kept_results = payload["kept_results"]
    evidence_status = "supported" if len(kept_results) >= MIN_EVIDENCE_SOURCES else "insufficient"
    confidence = "high" if evidence_status == "supported" else "none"

    if not kept_results:
        return {
            "content": (
                f"{knowledge_preflight_prefix}\n"
                "Evidence status: insufficient\n"
                "Confidence: none\n"
                f"No supported knowledge evidence was found for {query_to_search!r} "
                f"with score >= {min_score:.2f}. "
                "Tell the user the knowledge base does not contain enough evidence instead of guessing.\n\n"
                "User question:\n"
                f"{user_input}"
            ),
            "sources": [],
            "original_query": user_input,
            "rewritten_query": query_to_search,
            "evidence_status": "insufficient",
            "confidence": "none",
            "access_stats": payload.get("access_stats", {}),
        }

    sources = []
    lines = [
        (
            f"Evidence status: {evidence_status}\n"
            f"Confidence: {confidence}\n"
            f"Knowledge evidence for {query_to_search!r}: {len(kept_results)} result(s). "
            "Before answering, verify that each snippet is actually about the user's question. "
            "Start the final answer by explicitly saying that the following information comes from the knowledge base materials. "
            "Answer only from relevant snippets. Cite sources with their labels, such as [K1], only for claims directly supported by that snippet. "
            "If the snippets are unrelated or do not fully answer the question, say what is missing."
        ),
        "",
        "Sources:",
    ]

    for index, result in enumerate(kept_results, start=1):
        source_label = f"K{index}"
        result_metadata = result.metadata or {}
        page_start = result_metadata.get("page_start")
        page_end = result_metadata.get("page_end")
        page_text = ""
        if page_start and page_end:
            page_text = f" page={page_start}" if page_start == page_end else f" pages={page_start}-{page_end}"
        metadata_text = _format_source_metadata(result_metadata)
        sources.append(
            {
                "label": source_label,
                "document_id": result.document_id,
                "chunk_id": getattr(result, "chunk_id", f"{result.document_id}_chunk_{result.chunk_index:04d}"),
                "chunk_index": result.chunk_index,
                "score": result.score,
                "text": result.text,
                "metadata": result_metadata,
                "page_start": page_start,
                "page_end": page_end,
            }
        )
        lines.extend(
            [
                f"[{source_label}] document_id={result.document_id} chunk={result.chunk_index}{page_text} score={result.score:.3f}",
                f"metadata:{metadata_text}" if metadata_text else "metadata: unavailable",
                result.text,
                "",
            ]
        )

    rewritten_note = ""
    if query_to_search != user_input:
        rewritten_note = f"\n\n(Query was rewritten from: {user_input!r} to: {query_to_search!r} for better search results)"

    return {
        "content": (
            f"{knowledge_preflight_prefix}\n"
            f"{chr(10).join(lines).rstrip()}{rewritten_note}\n\n"
            "User question:\n"
            f"{user_input}"
        ),
        "sources": sources,
        "original_query": user_input,
        "rewritten_query": query_to_search,
        "evidence_status": evidence_status,
        "confidence": confidence,
        "access_stats": payload.get("access_stats", {}),
    }
