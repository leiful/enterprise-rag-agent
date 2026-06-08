# -*- coding: utf-8 -*-

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


QUERY_REWRITE_SYSTEM_PROMPT = (
    "You are a query rewriting assistant. Given the conversation history and the current user question, "
    "rewrite the question to be clear, complete, and optimized for semantic search. "
    "Remove ambiguity, resolve pronouns (it, this, that, they) by referring to the actual topic, "
    "and make the question specific. Only return the rewritten question, nothing else."
)

MULTI_QUERY_SYSTEM_PROMPT_TEMPLATE = (
    "You are a query generation assistant. Your task is to generate multiple different search queries "
    "based on a single user question. Each query should cover a different angle or aspect of the original "
    "question to improve the chances of finding relevant information.\n\n"
    "Generate exactly {num_queries} queries.\n"
    "Return a JSON object in the form {\"queries\": [...]} and no other text."
)


def build_query_rewrite_prompt():
    return ChatPromptTemplate.from_messages(
        [
            ("system", QUERY_REWRITE_SYSTEM_PROMPT),
            MessagesPlaceholder("history"),
            (
                "human",
                "Current user question: {user_input}\n\nPlease rewrite this question clearly and completely:",
            ),
        ]
    )


def build_multi_query_prompt(num_queries):
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                MULTI_QUERY_SYSTEM_PROMPT_TEMPLATE.format(num_queries=num_queries),
            ),
            ("human", "Original question: {user_input}\n\nGenerate the search queries now."),
        ]
    )


def build_answer_prompt(system_message_content):
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_message_content),
            MessagesPlaceholder("chat_history"),
            ("human", "{knowledge_preflight_content}"),
        ]
    )
