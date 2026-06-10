# -*- coding: utf-8 -*-

import json
import logging
import re

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from app_logging import get_logger, log_event
from chains.formatters import format_knowledge_preflight_payload
from chains.prompts import build_multi_query_prompt, build_query_rewrite_prompt
from config import (
    DEFAULT_KNOWLEDGE_MIN_SCORE,
    DEFAULT_KNOWLEDGE_TOP_K,
    ENABLE_RERANK,
    ENABLE_MULTI_QUERY,
    ENABLE_QUERY_COVERAGE_FILTER,
    ENABLE_QUERY_REWRITE,
    MULTI_QUERY_COUNT,
    QUERY_COVERAGE_MIN,
    RECALL_K,
    RERANK_MAX_CANDIDATES,
    RERANK_MIN_CANDIDATES,
)
from langchain_retriever import KnowledgeBaseRetriever
from vector_store import SearchResult, _who_query_subject


logger = get_logger("backend.retrieval")

QUERY_STOPWORDS = {
    "about", "after", "again", "also", "and", "any", "are", "can", "could",
    "current", "does", "find", "for", "from", "has", "have", "how", "into",
    "is", "it", "its", "me", "not", "of", "on", "or", "should", "that",
    "the", "their", "there", "this", "to", "what", "when", "where", "which",
    "who", "why", "with", "would", "you", "your",
}

CONTEXT_DEPENDENT_TERMS = {
    "it", "its", "they", "them", "this", "that", "these", "those", "same",
    "above", "previous", "earlier", "there", "he", "she", "his", "her",
    "它", "其", "他们", "她们", "这个", "那个", "这些", "那些", "上述", "上面",
    "前面", "之前", "刚才", "同样", "继续", "该", "此",
}


def extract_original_question(content, knowledge_preflight_prefix):
    if not isinstance(content, str) or not content.startswith(knowledge_preflight_prefix):
        return content

    lines = content.split("\n")
    found_user_question = False
    for line in lines:
        if line.strip() == "User question:":
            found_user_question = True
            continue
        if found_user_question:
            return line.strip()
    return content


def invoke_prompt_text(client, langchain_messages, extract_text_content, **kwargs):
    response = client.invoke(langchain_messages, **kwargs)
    return extract_text_content(getattr(response, "content", "")).strip()


def rewrite_query_with_history(client, messages, user_input, *, extract_text_content, knowledge_preflight_prefix):
    history = []
    for message in messages:
        role = message.get("role")
        if role in {"system", "tool"}:
            continue
        cleaned_content = extract_original_question(
            message.get("content", ""),
            knowledge_preflight_prefix,
        )
        if role == "user":
            history.append(HumanMessage(content=cleaned_content))
        elif role == "assistant":
            history.append(AIMessage(content=cleaned_content))

    prompt = build_query_rewrite_prompt()

    try:
        formatted_messages = prompt.format_messages(history=history, user_input=user_input)
        rewritten = invoke_prompt_text(
            client,
            formatted_messages,
            extract_text_content,
            temperature=0,
        )
        return rewritten.strip() or user_input
    except Exception as error:
        log_event(logger, logging.WARNING, "query_rewrite_failed", error=str(error))
        return user_input


def conversation_history_messages(messages, knowledge_preflight_prefix):
    history = []
    for message in messages or []:
        role = message.get("role")
        if role in {"system", "tool"}:
            continue
        content = extract_original_question(
            message.get("content", ""),
            knowledge_preflight_prefix,
        ).strip()
        if content:
            history.append({"role": role, "content": content})
    return history


def should_rewrite_query(messages, user_input, knowledge_preflight_prefix):
    history = conversation_history_messages(messages, knowledge_preflight_prefix)
    if len(history) < 2:
        return False

    normalized = (user_input or "").strip().lower()
    if not normalized:
        return False

    if len(normalized) <= 18:
        return True

    query_terms = set(re.findall(r"[\u4e00-\u9fff]{1,4}|[a-zA-Z]+", normalized))
    if query_terms & CONTEXT_DEPENDENT_TERMS:
        return True

    return bool(re.search(r"\b(what about|how about|and for|same as|continue)\b", normalized))


def generate_multiple_queries(client, user_input, num_queries, *, extract_text_content):
    prompt = build_multi_query_prompt(num_queries)

    try:
        formatted_messages = prompt.format_messages(user_input=user_input)
        result_text = invoke_prompt_text(
            client,
            formatted_messages,
            extract_text_content,
            temperature=0.7,
        )
        result = json.loads(result_text)
        queries = result if isinstance(result, list) else result.get("queries", [])
        queries = [query.strip() for query in queries if isinstance(query, str) and query.strip()]
        return queries[:num_queries] if queries else [user_input]
    except Exception as error:
        log_event(logger, logging.WARNING, "multi_query_generation_failed", error=str(error))
        return [user_input]


def resolve_retrieval_payload(
    client,
    payload,
    *,
    extract_text_content,
    knowledge_preflight_prefix,
):
    recall_k = payload.get("recall_k")
    if recall_k is None:
        recall_k = RECALL_K

    use_multi_query = payload.get("use_multi_query")
    if use_multi_query is None:
        use_multi_query = ENABLE_MULTI_QUERY

    num_queries = payload.get("num_queries")
    if num_queries is None:
        num_queries = MULTI_QUERY_COUNT

    top_k = payload.get("top_k")
    if top_k is None:
        top_k = DEFAULT_KNOWLEDGE_TOP_K

    min_score = payload.get("min_score")
    if min_score is None:
        min_score = DEFAULT_KNOWLEDGE_MIN_SCORE

    user_input = payload["user_input"]
    messages = payload.get("messages")

    query_to_search = user_input
    if ENABLE_QUERY_REWRITE and client and should_rewrite_query(messages, user_input, knowledge_preflight_prefix):
        query_to_search = rewrite_query_with_history(
            client,
            messages,
            user_input,
            extract_text_content=extract_text_content,
            knowledge_preflight_prefix=knowledge_preflight_prefix,
        )

    queries_to_search = [query_to_search]
    if use_multi_query and client:
        generated_queries = generate_multiple_queries(
            client,
            query_to_search,
            num_queries,
            extract_text_content=extract_text_content,
        )
        queries_to_search = list(dict.fromkeys([query_to_search] + generated_queries))

    return {
        **payload,
        "query_to_search": query_to_search,
        "queries_to_search": queries_to_search,
        "recall_k": recall_k,
        "top_k": top_k,
        "min_score": min_score,
        "use_multi_query": use_multi_query,
        "num_queries": num_queries,
    }


def build_retrieval_query_chain(client, *, extract_text_content, knowledge_preflight_prefix):
    return RunnableLambda(
        lambda payload: resolve_retrieval_payload(
            client,
            payload,
            extract_text_content=extract_text_content,
            knowledge_preflight_prefix=knowledge_preflight_prefix,
        )
    )


def cap_unrelated_who_results(results, *queries):
    who_subject = next((_who_query_subject(query) for query in queries if _who_query_subject(query)), None)
    if not who_subject:
        return results

    subject = who_subject.lower()
    for result in results:
        searchable_text = f"{result.document_id}\n{result.text}".lower()
        if subject not in searchable_text:
            result.score = min(result.score, 0.15)
    return results


def significant_query_terms(query):
    terms = []
    for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}|\d{2,}", query.lower()):
        normalized = term.strip("-_")
        if not normalized or normalized in QUERY_STOPWORDS:
            continue
        terms.append(normalized)
    return list(dict.fromkeys(terms))


def result_matches_query_terms(result, query, min_coverage=QUERY_COVERAGE_MIN):
    terms = significant_query_terms(query)
    if not terms:
        return True

    searchable_text = f"{result.document_id}\n{result.text}".lower()
    matched = sum(1 for term in terms if term in searchable_text)
    if len(terms) <= 2:
        return matched > 0
    return matched / len(terms) >= min_coverage


def filter_query_coverage(results, *queries):
    if not ENABLE_QUERY_COVERAGE_FILTER:
        return results, 0

    filtered = []
    filtered_count = 0
    usable_queries = [query for query in queries if query]
    for result in results:
        if any(result_matches_query_terms(result, query) for query in usable_queries):
            filtered.append(result)
        else:
            filtered_count += 1
    if results and not filtered:
        return results, 0
    return filtered, filtered_count


def query_term_coverage_score(result, *queries):
    all_terms = []
    for query in queries:
        all_terms.extend(significant_query_terms(query or ""))
    terms = list(dict.fromkeys(all_terms))
    if not terms:
        return 0.0

    searchable_text = f"{result.document_id}\n{result.text}".lower()
    matched = sum(1 for term in terms if term in searchable_text)
    return matched / len(terms)


def select_rerank_candidates(results, max_candidates, *queries):
    if len(results) <= max_candidates:
        return results

    selected = []
    seen_chunks = set()
    seen_documents = set()

    scored = []
    for index, result in enumerate(results):
        coverage = query_term_coverage_score(result, *queries)
        scored.append({
            "index": index,
            "result": result,
            "coverage": coverage,
            "score": float(result.score or 0.0),
        })

    for item in sorted(scored, key=lambda item: (item["coverage"], item["score"]), reverse=True):
        result = item["result"]
        if result.chunk_id in seen_chunks or result.document_id in seen_documents:
            continue
        selected.append(result)
        seen_chunks.add(result.chunk_id)
        seen_documents.add(result.document_id)
        if len(selected) >= max_candidates:
            return selected

    for item in sorted(scored, key=lambda item: item["score"], reverse=True):
        result = item["result"]
        if result.chunk_id in seen_chunks:
            continue
        selected.append(result)
        seen_chunks.add(result.chunk_id)
        if len(selected) >= max_candidates:
            return selected

    return selected


def retrieve_ranked_results(payload, *, rerank_with_dashscope):
    retriever = KnowledgeBaseRetriever(
        top_k=payload["recall_k"],
        category=payload.get("category"),
        tags=payload.get("tags"),
        file_extensions=payload.get("file_extensions"),
        departments=payload.get("departments"),
    )

    all_results = []
    seen_chunks = set()
    access_stats = {
        "candidate_count": 0,
        "kept_count": 0,
        "file_extension_filtered_count": 0,
        "metadata_filtered_count": 0,
        "access_filtered_count": 0,
        "inactive_filtered_count": 0,
        "older_version_filtered_count": 0,
        "query_coverage_filtered_count": 0,
        "queries": [],
        "departments_scope": payload.get("departments"),
        "recall_k": payload["recall_k"],
        "top_k": payload["top_k"],
        "min_score": payload["min_score"],
        "rerank_applied": False,
    }
    for search_query in payload["queries_to_search"]:
        documents = retriever.invoke(search_query)
        query_stats = dict(retriever.last_access_stats or {})
        access_stats["queries"].append(query_stats)
        for key in (
            "candidate_count",
            "kept_count",
            "file_extension_filtered_count",
            "metadata_filtered_count",
            "access_filtered_count",
            "inactive_filtered_count",
            "older_version_filtered_count",
        ):
            access_stats[key] += int(query_stats.get(key) or 0)
        for document in documents:
            metadata = document.metadata or {}
            result = SearchResult(
                score=float(metadata.get("score", 0.0)),
                chunk_id=metadata.get("chunk_id", ""),
                document_id=metadata.get("document_id", ""),
                chunk_index=int(metadata.get("chunk_index", 0)),
                text=document.page_content,
                metadata={
                    key: value
                    for key, value in metadata.items()
                    if key not in {"score", "chunk_id", "document_id", "chunk_index"}
                },
            )
            if result.chunk_id in seen_chunks:
                continue
            seen_chunks.add(result.chunk_id)
            all_results.append(result)

    kept_results = all_results
    should_rerank = ENABLE_RERANK and len(all_results) >= max(payload["top_k"] * 3, RERANK_MIN_CANDIDATES)
    if should_rerank:
        access_stats["rerank_applied"] = True
        rerank_candidates = select_rerank_candidates(
            all_results,
            RERANK_MAX_CANDIDATES,
            payload["user_input"],
            payload["query_to_search"],
        )
        access_stats["rerank_candidate_count"] = len(rerank_candidates)
        kept_results = rerank_with_dashscope(
            payload["query_to_search"],
            rerank_candidates,
            top_k=payload["top_k"] * 2,
        )

    kept_results = cap_unrelated_who_results(
        kept_results,
        payload["user_input"],
        payload["query_to_search"],
    )
    kept_results, query_coverage_filtered_count = filter_query_coverage(
        kept_results,
        payload["user_input"],
        payload["query_to_search"],
    )
    access_stats["query_coverage_filtered_count"] = query_coverage_filtered_count

    filtered_results = [
        result for result in kept_results
        if result.score >= payload["min_score"]
    ][: payload["top_k"]]

    log_event(
        logger,
        logging.INFO,
        "retrieval_completed",
        query_count=len(payload["queries_to_search"]),
        candidate_count=len(all_results),
        raw_candidate_count=access_stats["candidate_count"],
        access_filtered_count=access_stats["access_filtered_count"],
        result_count=len(filtered_results),
        top_k=payload["top_k"],
        recall_k=payload["recall_k"],
        min_score=payload["min_score"],
        rerank_enabled=should_rerank,
        rerank_max_candidates=RERANK_MAX_CANDIDATES if should_rerank else 0,
    )

    return {
        **payload,
        "kept_results": filtered_results,
        "access_stats": access_stats,
    }


def build_retrieval_results_chain(
    client,
    *,
    extract_text_content,
    knowledge_preflight_prefix,
    rerank_with_dashscope,
):
    return (
        build_retrieval_query_chain(
            client,
            extract_text_content=extract_text_content,
            knowledge_preflight_prefix=knowledge_preflight_prefix,
        )
        | RunnableLambda(lambda payload: retrieve_ranked_results(payload, rerank_with_dashscope=rerank_with_dashscope))
    )


def build_knowledge_preflight_chain(
    client,
    *,
    extract_text_content,
    knowledge_preflight_prefix,
    rerank_with_dashscope,
):
    return (
        build_retrieval_results_chain(
            client,
            extract_text_content=extract_text_content,
            knowledge_preflight_prefix=knowledge_preflight_prefix,
            rerank_with_dashscope=rerank_with_dashscope,
        )
        | RunnableLambda(
            lambda payload: format_knowledge_preflight_payload(
                payload,
                knowledge_preflight_prefix=knowledge_preflight_prefix,
            )
        )
    )
