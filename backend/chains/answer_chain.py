# -*- coding: utf-8 -*-

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough

from chains.prompts import build_answer_prompt as build_answer_prompt_template


def to_answer_history(messages):
    history = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "system":
            continue
        if role == "user":
            history.append(HumanMessage(content=content))
        elif role == "assistant":
            history.append(AIMessage(content=content))
    return history


def to_answer_chain_payload(payload):
    knowledge_preflight = payload["knowledge_preflight"]
    return {
        "chat_history": to_answer_history(payload["messages"]),
        "knowledge_preflight_content": knowledge_preflight["content"],
        "knowledge_preflight": knowledge_preflight,
        "sources": knowledge_preflight["sources"],
    }


class ClientRunnable(Runnable):
    def __init__(self, client):
        self.client = client

    def invoke(self, input, config=None, **kwargs):
        return self.client.invoke(input, **kwargs)

    def stream(self, input, config=None, **kwargs):
        if hasattr(self.client, "stream"):
            yield from self.client.stream(input, **kwargs)
            return
        yield self.invoke(input, config=config, **kwargs)


def as_runnable_client(client):
    if isinstance(client, Runnable):
        return client
    return ClientRunnable(client)


def build_answer_prompt(system_message_content):
    return build_answer_prompt_template(system_message_content)


def build_answer_context_chain(knowledge_preflight_chain):
    return (
        RunnablePassthrough.assign(
            knowledge_preflight=RunnableLambda(
                lambda payload: payload["knowledge_preflight"]
                if payload.get("knowledge_preflight") is not None
                else knowledge_preflight_chain.invoke(payload)
            )
        )
        | RunnableLambda(to_answer_chain_payload)
    )


def build_prepared_answer_text_chain(client, system_message_content):
    return build_answer_prompt(system_message_content) | as_runnable_client(client) | StrOutputParser()


def build_answer_response_chain(client, knowledge_preflight_chain, system_message_content):
    prepared_answer_chain = build_prepared_answer_text_chain(client, system_message_content)
    return (
        build_answer_context_chain(knowledge_preflight_chain)
        | RunnablePassthrough.assign(answer=prepared_answer_chain)
        | RunnableLambda(
            lambda payload: {
                "answer": payload["answer"],
                "sources": payload["sources"],
                "knowledge_preflight": payload["knowledge_preflight"],
            }
        )
    )
