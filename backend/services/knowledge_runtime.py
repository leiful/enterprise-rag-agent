# -*- coding: utf-8 -*-

from adapters.content_adapter import extract_text_content
from app_logging import get_logger, log_event
from chains.retrieval_chain import (
    build_knowledge_preflight_chain as build_knowledge_preflight_lcel_chain,
    build_retrieval_results_chain as build_retrieval_results_lcel_chain,
    generate_multiple_queries as generate_multiple_queries_lcel,
    rewrite_query_with_history as rewrite_query_with_history_lcel,
)
from services.rerank_service import rerank_with_dashscope
from config import DEFAULT_KNOWLEDGE_MIN_SCORE, DEFAULT_KNOWLEDGE_TOP_K


KNOWLEDGE_PREFLIGHT_PREFIX = "Knowledge base preflight result:"
logger = get_logger("backend.knowledge_runtime")


def rewrite_query_with_history(client, messages, user_input):
    return rewrite_query_with_history_lcel(
        client,
        messages,
        user_input,
        extract_text_content=extract_text_content,
        knowledge_preflight_prefix=KNOWLEDGE_PREFLIGHT_PREFIX,
    )


def generate_multiple_queries(client, user_input, num_queries=3):
    return generate_multiple_queries_lcel(
        client,
        user_input,
        num_queries,
        extract_text_content=extract_text_content,
    )


def build_retrieval_results_chain(client):
    return build_retrieval_results_lcel_chain(
        client,
        extract_text_content=extract_text_content,
        knowledge_preflight_prefix=KNOWLEDGE_PREFLIGHT_PREFIX,
        rerank_with_dashscope=rerank_with_dashscope,
    )


def search_knowledge_results(
    query,
    top_k=None,
    min_score=None,
    recall_k=None,
    category=None,
    tags=None,
    file_extensions=None,
    departments=None,
    client=None,
    use_multi_query=None,
    num_queries=None,
):
    payload = search_knowledge_payload(
        query,
        top_k=top_k,
        min_score=min_score,
        recall_k=recall_k,
        category=category,
        tags=tags,
        file_extensions=file_extensions,
        departments=departments,
        client=client,
        use_multi_query=use_multi_query,
        num_queries=num_queries,
    )
    return payload["kept_results"]


def search_knowledge_payload(
    query,
    top_k=None,
    min_score=None,
    recall_k=None,
    category=None,
    tags=None,
    file_extensions=None,
    departments=None,
    client=None,
    use_multi_query=None,
    num_queries=None,
):
    return build_retrieval_results_chain(client).invoke(
        {
            "user_input": query,
            "messages": None,
            "top_k": top_k,
            "min_score": min_score,
            "recall_k": recall_k,
            "category": category,
            "tags": tags,
            "file_extensions": file_extensions,
            "departments": departments,
            "use_multi_query": use_multi_query,
            "num_queries": num_queries,
        }
    )


def build_knowledge_preflight_chain(client):
    return build_knowledge_preflight_lcel_chain(
        client,
        extract_text_content=extract_text_content,
        knowledge_preflight_prefix=KNOWLEDGE_PREFLIGHT_PREFIX,
        rerank_with_dashscope=rerank_with_dashscope,
    )


def build_knowledge_preflight(
    user_input,
    client=None,
    messages=None,
    category=None,
    tags=None,
    file_extensions=None,
    departments=None,
    use_multi_query=None,
):
    try:
        return build_knowledge_preflight_chain(client).invoke(
            {
                "user_input": user_input,
                "messages": messages,
                "top_k": DEFAULT_KNOWLEDGE_TOP_K,
                "min_score": DEFAULT_KNOWLEDGE_MIN_SCORE,
                "category": category,
                "tags": tags,
                "file_extensions": file_extensions,
                "departments": departments,
                "use_multi_query": use_multi_query,
            }
        )
    except Exception as error:
        log_event(logger, 40, "knowledge_preflight_failed", error=str(error))
        return {
            "content": (
                f"{KNOWLEDGE_PREFLIGHT_PREFIX}\n"
                f"search_knowledge error: {error}\n\n"
                "User question:\n"
                f"{user_input}"
            ),
            "sources": [],
            "access_stats": {},
        }


def build_user_message_with_knowledge_preflight(user_input, client=None, messages=None):
    return build_knowledge_preflight(user_input, client, messages)["content"]
