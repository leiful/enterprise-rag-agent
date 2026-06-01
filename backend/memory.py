# -*- coding: utf-8 -*-

import json
from datetime import datetime

from config import LOG_FILE, MAX_HISTORY_MESSAGES, SYSTEM_MESSAGE


def message_role(message):
    return message.get("role")


def has_tool_calls(message):
    return bool(message.get("tool_calls"))


def append_log_entries(entries):
    # SQLite stores chat history; this JSONL file is only for debugging events.
    timestamp = datetime.now().isoformat(timespec="seconds")

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        for message in entries:
            record = {
                "timestamp": timestamp,
                "message": message,
            }
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def trim_messages(messages):
    # Keep message history bounded to avoid unbounded context growth.
    system_messages = [
        message for message in messages
        if message_role(message) == "system"
    ]
    history_messages = [
        message for message in messages
        if message_role(message) != "system"
    ]

    kept_history = history_messages[-MAX_HISTORY_MESSAGES:]

    # History cannot start with a tool message because it needs a matching tool call.
    while kept_history and message_role(kept_history[0]) == "tool":
        kept_history.pop(0)

    # Do not keep history starting in the middle of a tool-call exchange.
    if kept_history and message_role(kept_history[0]) == "assistant" and has_tool_calls(kept_history[0]):
        kept_history.pop(0)

        while kept_history and message_role(kept_history[0]) == "tool":
            kept_history.pop(0)

    messages[:] = system_messages + kept_history
