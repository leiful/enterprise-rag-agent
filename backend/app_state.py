# -*- coding: utf-8 -*-

from collections import Counter
import threading

from fastapi import HTTPException, status

from config import (
    CHAT_MAX_CONCURRENT_PER_CONVERSATION,
    CHAT_MAX_CONCURRENT_PER_USER,
    CHAT_MAX_CONCURRENT_REQUESTS,
)


client = None
startup_error = None
config_issues = []
SESSION_COOKIE = "agent_session"
knowledge_version = 0
_knowledge_version_lock = threading.Lock()


def bump_knowledge_version():
    global knowledge_version
    with _knowledge_version_lock:
        knowledge_version += 1

chat_admission_lock = threading.Lock()
active_chat_total = 0
active_chat_by_user = Counter()
active_chat_by_conversation = Counter()


class ChatAdmission:
    def __init__(self, user_id, conversation_id):
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.acquired = False

    def __enter__(self):
        global active_chat_total
        with chat_admission_lock:
            if active_chat_total >= CHAT_MAX_CONCURRENT_REQUESTS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Chat is busy. Please try again shortly.",
                    headers={"Retry-After": "5"},
                )
            if active_chat_by_user[self.user_id] >= CHAT_MAX_CONCURRENT_PER_USER:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="You already have a chat request running. Please wait for it to finish.",
                    headers={"Retry-After": "5"},
                )
            if active_chat_by_conversation[self.conversation_id] >= CHAT_MAX_CONCURRENT_PER_CONVERSATION:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="This conversation is already answering another message.",
                    headers={"Retry-After": "5"},
                )

            active_chat_total += 1
            active_chat_by_user[self.user_id] += 1
            active_chat_by_conversation[self.conversation_id] += 1
            self.acquired = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        global active_chat_total
        if not self.acquired:
            return
        with chat_admission_lock:
            active_chat_total = max(0, active_chat_total - 1)
            active_chat_by_user[self.user_id] -= 1
            active_chat_by_conversation[self.conversation_id] -= 1
            if active_chat_by_user[self.user_id] <= 0:
                del active_chat_by_user[self.user_id]
            if active_chat_by_conversation[self.conversation_id] <= 0:
                del active_chat_by_conversation[self.conversation_id]


def current_chat_admission_status():
    with chat_admission_lock:
        return {
            "active": active_chat_total,
            "max_concurrent": CHAT_MAX_CONCURRENT_REQUESTS,
            "max_per_user": CHAT_MAX_CONCURRENT_PER_USER,
            "max_per_conversation": CHAT_MAX_CONCURRENT_PER_CONVERSATION,
        }
