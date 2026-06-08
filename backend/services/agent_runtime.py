# -*- coding: utf-8 -*-

from memory import append_log_entries, trim_messages
from model_client import format_model_error


def run_agent(
    client,
    messages,
    user_input,
    *,
    build_answer_response_chain,
    knowledge_preflight=None,
    return_sources=False,
):
    new_messages = []
    response_chain = build_answer_response_chain(client)

    try:
        chain_result = response_chain.invoke(
            {
                "messages": messages,
                "user_input": user_input,
                "knowledge_preflight": knowledge_preflight,
            }
        )
    except Exception as error:
        fallback_preflight = knowledge_preflight or {"sources": []}
        error_message = {"role": "assistant", "content": format_model_error(error)}
        messages.append(error_message)
        new_messages.append(error_message)
        append_log_entries(new_messages)
        trim_messages(messages)
        if return_sources:
            return {"answer": error_message["content"], "sources": fallback_preflight["sources"]}
        return error_message["content"]

    knowledge_preflight = chain_result["knowledge_preflight"]
    user_message = {"role": "user", "content": knowledge_preflight["content"]}
    assistant_message = {"role": "assistant", "content": chain_result["answer"]}

    messages.append(user_message)
    messages.append(assistant_message)
    new_messages.extend([user_message, assistant_message])

    append_log_entries(new_messages)
    trim_messages(messages)
    if return_sources:
        return {"answer": chain_result["answer"], "sources": knowledge_preflight["sources"]}
    return chain_result["answer"]


def run_agent_stream(
    client,
    messages,
    user_input,
    *,
    build_answer_context_chain,
    build_prepared_answer_text_chain,
    knowledge_preflight=None,
):
    new_messages = []
    context_chain = build_answer_context_chain(client)
    prepared_answer_chain = build_prepared_answer_text_chain(client)

    try:
        prepared_payload = context_chain.invoke(
            {
                "messages": messages,
                "user_input": user_input,
                "knowledge_preflight": knowledge_preflight,
            }
        )
    except Exception as error:
        error_message = {"role": "assistant", "content": format_model_error(error)}
        messages.append(error_message)
        new_messages.append(error_message)
        append_log_entries(new_messages)
        trim_messages(messages)
        yield error_message["content"]
        return

    user_message = {"role": "user", "content": prepared_payload["knowledge_preflight"]["content"]}
    messages.append(user_message)
    new_messages.append(user_message)

    final_answer = []
    try:
        for content in prepared_answer_chain.stream(prepared_payload):
            final_answer.append(content)
            yield content
    except Exception as error:
        error_text = format_model_error(error)
        final_answer.append(error_text)
        yield error_text

    final_message = {"role": "assistant", "content": "".join(final_answer)}
    messages.append(final_message)
    new_messages.append(final_message)
    append_log_entries(new_messages)
    trim_messages(messages)
