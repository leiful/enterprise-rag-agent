# -*- coding: utf-8 -*-

from datetime import datetime

import vector_store

MAX_KNOWLEDGE_RESULTS = 5


def get_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def search_knowledge(query, top_k=3, min_score=0.3):
    return search_knowledge_with_sources(query, top_k, min_score)["text"]


def search_knowledge_with_sources(query, top_k=3, min_score=0.3):
    if not query:
        return {
            "text": "search_knowledge error: query is required",
            "sources": [],
        }

    if top_k < 1:
        top_k = 3

    top_k = min(top_k, MAX_KNOWLEDGE_RESULTS)

    try:
        results = vector_store.search(query, top_k=top_k)
    except Exception as error:
        return {
            "text": f"search_knowledge error: {error}",
            "sources": [],
        }

    kept_results = [
        result for result in results
        if result.score >= min_score
    ]

    if not kept_results:
        return {
            "text": (
                f"No supported knowledge evidence was found for {query!r} "
                f"with score >= {min_score:.2f}. "
                "Tell the user the knowledge base does not contain enough evidence instead of guessing."
            ),
            "sources": [],
        }

    lines = [
        (
            f"Knowledge evidence for {query!r}: {len(kept_results)} result(s). "
            "Before answering, verify that each snippet is actually about the user's question. "
            "Answer only from relevant snippets. Cite sources with their labels, such as [K1], only for claims directly supported by that snippet. "
            "If the snippets are unrelated or do not fully answer the question, say what is missing."
        ),
        "",
        "Sources:",
    ]

    sources = []
    for index, result in enumerate(kept_results, start=1):
        source_label = f"K{index}"
        sources.append({
            "label": source_label,
            "document_id": result.document_id,
            "chunk_id": getattr(result, "chunk_id", f"{result.document_id}_chunk_{result.chunk_index:04d}"),
            "chunk_index": result.chunk_index,
            "score": result.score,
            "text": result.text,
        })
        lines.extend([
            (
                f"[{source_label}] document_id={result.document_id} "
                f"chunk={result.chunk_index} score={result.score:.3f}"
            ),
            result.text,
            "",
        ])

    return {
        "text": "\n".join(lines).rstrip(),
        "sources": sources,
    }


def call_tool(name, arguments):
    if name == "get_time":
        return get_time()

    if name == "search_knowledge":
        return search_knowledge(
            arguments["query"],
            arguments.get("top_k", 3),
            arguments.get("min_score", 0.3),
        )

    return f"unknown tool: {name}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current local time.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search the indexed knowledge base with vector search. Use this only when the user asks about uploaded notes, project documentation, deployment notes, policies, or knowledge base content. Do not use it for ordinary world-knowledge questions or public figures unless the user explicitly asks to search the knowledge base. The result contains citation labels, source document ids, chunk indexes, scores, and text snippets. Ground the answer in relevant snippets and cite labels like [K1] only for directly supported claims.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The natural-language question or search phrase to find in the knowledge base.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": f"The maximum number of knowledge chunks to return. Defaults to 3 and cannot exceed {MAX_KNOWLEDGE_RESULTS}.",
                    },
                    "min_score": {
                        "type": "number",
                        "description": "Minimum cosine similarity score to keep. Defaults to 0.3.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
