# -*- coding: utf-8 -*-

from config import (
    DEFAULT_KNOWLEDGE_MIN_SCORE,
    DEFAULT_KNOWLEDGE_TOP_K,
    NO_EVIDENCE_ANSWER,
    STRICT_KNOWLEDGE_ABSTENTION,
    SYSTEM_MESSAGE,
)
from chains.answer_chain import (
    build_answer_context_chain as build_answer_context_lcel_chain,
    build_answer_response_chain as build_answer_response_lcel_chain,
    build_prepared_answer_text_chain as build_prepared_answer_text_lcel_chain,
)
from model_client import create_client
from services.agent_runtime import (
    run_agent as run_agent_runtime,
    run_agent_stream as run_agent_stream_runtime,
)
from services.knowledge_runtime import (
    KNOWLEDGE_PREFLIGHT_PREFIX,
    build_knowledge_preflight as build_knowledge_preflight_runtime,
    build_knowledge_preflight_chain as build_knowledge_preflight_chain_runtime,
    build_retrieval_results_chain as build_retrieval_results_chain_runtime,
    generate_multiple_queries as generate_multiple_queries_runtime,
    rewrite_query_with_history as rewrite_query_with_history_runtime,
    search_knowledge_payload as search_knowledge_payload_runtime,
    search_knowledge_results as search_knowledge_results_runtime,
)
from services.rerank_service import rerank_with_dashscope
from services.tool_runtime import (
    confirm_tool_call as confirm_tool_call_runtime,
    run_tool_call as run_tool_call_runtime,
)


def build_answer_context_chain(client):
    return build_answer_context_lcel_chain(
        build_knowledge_preflight_chain(client)
    )


def build_prepared_answer_text_chain(client):
    return build_prepared_answer_text_lcel_chain(
        client,
        SYSTEM_MESSAGE["content"],
    )


def build_answer_response_chain(client):
    return build_answer_response_lcel_chain(
        client,
        build_knowledge_preflight_chain(client),
        SYSTEM_MESSAGE["content"],
    )


def rewrite_query_with_history(client, messages, user_input):
    return rewrite_query_with_history_runtime(client, messages, user_input)


def generate_multiple_queries(client, user_input, num_queries=3):
    return generate_multiple_queries_runtime(client, user_input, num_queries)


def build_retrieval_results_chain(client):
    return build_retrieval_results_chain_runtime(client)


def search_knowledge_results(
    query,
    top_k=DEFAULT_KNOWLEDGE_TOP_K,
    min_score=DEFAULT_KNOWLEDGE_MIN_SCORE,
    recall_k=None,
    category=None,
    tags=None,
    file_extensions=None,
    departments=None,
    client=None,
    use_multi_query=None,
    num_queries=None,
):
    return search_knowledge_results_runtime(
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


def search_knowledge_payload(
    query,
    top_k=DEFAULT_KNOWLEDGE_TOP_K,
    min_score=DEFAULT_KNOWLEDGE_MIN_SCORE,
    recall_k=None,
    category=None,
    tags=None,
    file_extensions=None,
    departments=None,
    client=None,
    use_multi_query=None,
    num_queries=None,
):
    return search_knowledge_payload_runtime(
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


def build_user_message_with_knowledge_preflight(user_input, client=None, messages=None):
    return build_knowledge_preflight(user_input, client, messages)["content"]


def build_knowledge_preflight_chain(client):
    return build_knowledge_preflight_chain_runtime(client)


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
    return build_knowledge_preflight_runtime(
        user_input,
        client=client,
        messages=messages,
        category=category,
        tags=tags,
        file_extensions=file_extensions,
        departments=departments,
        use_multi_query=use_multi_query,
    )


def confirm_tool_call(tool_name, tool_args):
    return confirm_tool_call_runtime(tool_name, tool_args)


def run_tool_call(tool_call, remaining_file_read_lines, confirm_callback=confirm_tool_call):
    return run_tool_call_runtime(tool_call, remaining_file_read_lines, confirm_callback=confirm_callback)


def run_agent(client, messages, user_input, max_steps=5, knowledge_preflight=None, return_sources=False):
    if STRICT_KNOWLEDGE_ABSTENTION and knowledge_preflight and not knowledge_preflight.get("sources"):
        no_evidence_answer = NO_EVIDENCE_ANSWER
        messages.append({"role": "user", "content": knowledge_preflight["content"]})
        messages.append({"role": "assistant", "content": no_evidence_answer})
        if return_sources:
            return {"answer": no_evidence_answer, "sources": [], "knowledge_preflight": knowledge_preflight}
        return no_evidence_answer

    return run_agent_runtime(
        client,
        messages,
        user_input,
        build_answer_response_chain=build_answer_response_chain,
        knowledge_preflight=knowledge_preflight,
        return_sources=return_sources,
    )


def run_agent_stream(client, messages, user_input, max_steps=5, knowledge_preflight=None):
    if STRICT_KNOWLEDGE_ABSTENTION and knowledge_preflight and not knowledge_preflight.get("sources"):
        no_evidence_answer = NO_EVIDENCE_ANSWER
        messages.append({"role": "user", "content": knowledge_preflight["content"]})
        messages.append({"role": "assistant", "content": no_evidence_answer})
        yield no_evidence_answer
        return

    yield from run_agent_stream_runtime(
        client,
        messages,
        user_input,
        build_answer_context_chain=build_answer_context_chain,
        build_prepared_answer_text_chain=build_prepared_answer_text_chain,
        knowledge_preflight=knowledge_preflight,
    )


def main():
    try:
        client = create_client()
    except RuntimeError as error:
        print(f"Startup error: {error}")
        return

    messages = [SYSTEM_MESSAGE.copy()]
    print("AI Agent started.")
    print("Try: what time is it now?")
    print("Try: search the knowledge base for deployment notes")
    print("Type q to quit.")

    while True:
        user_input = input("\nYou: ").strip()
        if user_input == "q":
            break
        answer = run_agent(client, messages, user_input)
        print(f"AI: {answer}")


if __name__ == "__main__":
    main()
