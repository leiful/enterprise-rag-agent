# -*- coding: utf-8 -*-

from adapters.content_adapter import extract_text_content
from config import (
    DEFAULT_KNOWLEDGE_MIN_SCORE,
    DEFAULT_KNOWLEDGE_TOP_K,
    NO_EVIDENCE_ANSWER,
    SYSTEM_MESSAGE,
)
from graph.graph import build_agent_graph, build_answer_stream_graph, should_abstain
from chains.answer_chain import (
    build_answer_context_chain as build_answer_context_lcel_chain,
    build_answer_response_chain as build_answer_response_lcel_chain,
    build_prepared_answer_text_chain as build_prepared_answer_text_lcel_chain,
)
from model_client import create_client
from services.agent_runtime import run_agent_stream as run_agent_stream_runtime
from services.knowledge_runtime import (
    KNOWLEDGE_PREFLIGHT_PREFIX,
    build_knowledge_preflight as build_knowledge_preflight_runtime,
    build_knowledge_preflight_chain as build_knowledge_preflight_chain_runtime,
    search_knowledge_payload as search_knowledge_payload_runtime,
)
from services.rerank_service import rerank_with_dashscope

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



def run_agent(
    client, messages, user_input, max_steps=5, knowledge_preflight=None, return_sources=False,
    category=None, tags=None, file_extensions=None, departments=None, use_multi_query=None,
    thread_id=None, user_id=None,
):
    graph = build_agent_graph(
        build_answer_response_chain,
        extract_text_content=extract_text_content,
        knowledge_preflight_prefix=KNOWLEDGE_PREFLIGHT_PREFIX,
        rerank_with_dashscope=rerank_with_dashscope,
        system_message_content=SYSTEM_MESSAGE["content"],
        enable_checkpointer=thread_id is not None,
    )
    config = {"configurable": {"thread_id": str(thread_id)}} if thread_id else None
    state = {
        "_client": client,
        "_return_sources": return_sources,
        "user_input": user_input,
        "user_id": user_id,
        "knowledge_preflight": knowledge_preflight,
        "category": category,
        "tags": tags,
        "file_extensions": file_extensions,
        "departments": departments,
        "use_multi_query": use_multi_query,
        "answer": "",
        "sources": [],
    }
    if messages:
        state["messages"] = messages
    result = graph.invoke(state, config=config)

    if return_sources:
        return {
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "knowledge_preflight": result.get("knowledge_preflight"),
        }
    return result["answer"]


def run_agent_stream(
    client, messages, user_input, max_steps=5, knowledge_preflight=None,
    category=None, tags=None, file_extensions=None, departments=None, use_multi_query=None,
):
    if knowledge_preflight is None:
        knowledge_preflight = build_knowledge_preflight_runtime(
            user_input,
            client=client,
            messages=messages,
            category=category,
            tags=tags,
            file_extensions=file_extensions,
            departments=departments,
            use_multi_query=use_multi_query,
        )

    if should_abstain(knowledge_preflight):
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


def run_agent_stream_with_preflight(client, messages, user_input, *, departments=None, thread_id=None, user_id=None):
    retrieval_graph = build_agent_graph(
        build_answer_response_chain,
        extract_text_content=extract_text_content,
        knowledge_preflight_prefix=KNOWLEDGE_PREFLIGHT_PREFIX,
        rerank_with_dashscope=rerank_with_dashscope,
        system_message_content=SYSTEM_MESSAGE["content"],
        enable_checkpointer=thread_id is not None,
    )
    config = {"configurable": {"thread_id": str(thread_id)}} if thread_id else None
    state_input = {
        "_client": client,
        "_streaming_mode": True,
        "user_input": user_input,
        "user_id": user_id,
        "knowledge_preflight": None,
        "departments": departments,
        "answer": "",
        "sources": [],
    }
    if messages:
        state_input["messages"] = messages
    result = retrieval_graph.invoke(state_input, config=config)

    if result.get("_route") == "abstain":
        def abstain_gen():
            yield result["answer"]
        return abstain_gen(), []

    sources = result.get("sources", [])

    stream_graph = build_answer_stream_graph(
        build_answer_context_chain,
        build_prepared_answer_text_chain,
    )

    def token_stream():
        for event in stream_graph.stream(
            {
                "_client": client,
                "messages": messages,
                "user_input": user_input,
                "knowledge_preflight": result.get("knowledge_preflight"),
                "answer": "",
                "sources": [],
            },
            stream_mode="custom",
        ):
            yield event

    return token_stream(), sources


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
