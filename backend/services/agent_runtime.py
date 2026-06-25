# -*- coding: utf-8 -*-

from memory import append_log_entries, trim_messages
from config import MODEL
from model_client import format_model_error
from app_logging import request_id_var
from model_usage import record_model_usage


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
    record_model_usage(
        provider="deepseek",
        model=MODEL,
        operation="chat_stream",
        request_id=request_id_var.get(),
        input_texts=[message.get("content", "") for message in messages] + [user_input],
        output_texts=[final_message["content"]],
        document_count=len(prepared_payload.get("knowledge_preflight", {}).get("sources") or []),
    )
    messages.append(final_message)
    new_messages.append(final_message)
    append_log_entries(new_messages)
    trim_messages(messages)
