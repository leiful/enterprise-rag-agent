from typing import Any, TypedDict

from config import MAX_HISTORY_TOKENS


def count_tokens(text):
    if not text:
        return 0
    return max(1, len(str(text)) // 2)


def trim_messages_by_token(messages, max_tokens=MAX_HISTORY_TOKENS):
    if not messages:
        return messages

    system_msgs = [m for m in messages if m.get("role") == "system"]
    history = [m for m in messages if m.get("role") != "system"]

    if not history:
        return messages

    total = sum(count_tokens(m.get("content", "")) for m in history)
    while total > max_tokens and len(history) > 1:
        removed = history.pop(0)
        total -= count_tokens(removed.get("content", ""))

    return system_msgs + history


class AgentState(TypedDict, total=False):
    messages: list[dict]
    user_input: str
    user_id: str
    knowledge_preflight: dict | None
    answer: str
    sources: list
    category: str | None
    tags: list[str] | None
    file_extensions: list[str] | None
    departments: list[str] | None
    use_multi_query: bool | None
    query_to_search: str
    queries_to_search: list[str]
    kept_results: list
    access_stats: dict
    _route: str
    _chain_ok: bool
    _client: Any
    _return_sources: bool
    _streaming_mode: bool
    _extraction_counter: int
