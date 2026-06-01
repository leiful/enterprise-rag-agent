# -*- coding: utf-8 -*-

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")


MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
APP_USERNAME = os.environ.get("APP_USERNAME", "").strip()
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
SESSION_MAX_AGE_SECONDS = int(os.environ.get("SESSION_MAX_AGE_SECONDS", "604800"))
DATABASE_FILE = os.environ.get("DATABASE_FILE", str(PROJECT_ROOT / "agent.db"))

MAX_HISTORY_MESSAGES = 20
MAX_FILE_READ_LINES_PER_TURN = 120
LOG_FILE = "chat_log.jsonl"

ALLOWED_READ_EXTENSIONS = {".py", ".md", ".txt", ".json", ".jsonl"}
EXCLUDED_READ_FILES = {".env", LOG_FILE, "todos.json"}
MAX_READ_LINES = 120
MAX_SEARCH_MATCHES = 20
MAX_PROJECT_SEARCH_MATCHES = 30

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "You are a project assistant inside a private web console. "
        "Answer the user's question directly in Chinese when the user writes Chinese. "
        "Use tools only when they are necessary for the user's request. "
        "Do not inspect project files just because the user asks a casual identity question like 'who am I'. "
        "For that, answer that they are the signed-in user you are chatting with, and explain that you do not know more personal identity unless the app provides it."
    ),
}
