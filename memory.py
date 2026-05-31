# -*- coding: utf-8 -*-

import json
import os
from datetime import datetime

from config import HISTORY_FILE, LOG_FILE, MAX_HISTORY_MESSAGES, SYSTEM_MESSAGE


def message_role(message):
    # 从普通 message 字典中读取 role。
    return message.get("role")


def has_tool_calls(message):
    # 判断 assistant message 是否包含工具调用请求。
    return bool(message.get("tool_calls"))


def load_messages():
    # 从本地 JSON 恢复长期记忆；没有历史时从 system message 开始。
    if not os.path.exists(HISTORY_FILE):
        return [SYSTEM_MESSAGE.copy()]

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            messages = json.load(file)
    except (OSError, json.JSONDecodeError):
        return [SYSTEM_MESSAGE.copy()]

    if not messages or message_role(messages[0]) != "system":
        messages.insert(0, SYSTEM_MESSAGE.copy())

    return messages


def save_messages(messages):
    # 保存当前对话历史，脚本重启后可以恢复。
    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(messages, file, ensure_ascii=False, indent=2)


def append_log_entries(entries):
    # 追加完整日志，不裁剪；用于排查、审计和回放。
    timestamp = datetime.now().isoformat(timespec="seconds")

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        for message in entries:
            record = {
                "timestamp": timestamp,
                "message": message,
            }
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def trim_messages(messages):
    # 控制记忆长度，避免 token 成本和上下文长度无限增长。
    system_messages = [
        message for message in messages
        if message_role(message) == "system"
    ]
    history_messages = [
        message for message in messages
        if message_role(message) != "system"
    ]

    kept_history = history_messages[-MAX_HISTORY_MESSAGES:]

    # tool message 不能出现在历史开头，因为它需要对应的 tool_call。
    while kept_history and message_role(kept_history[0]) == "tool":
        kept_history.pop(0)

    # 不要从一次工具调用流程的中间开始保留历史。
    if kept_history and message_role(kept_history[0]) == "assistant" and has_tool_calls(kept_history[0]):
        kept_history.pop(0)

        while kept_history and message_role(kept_history[0]) == "tool":
            kept_history.pop(0)

    messages[:] = system_messages + kept_history
