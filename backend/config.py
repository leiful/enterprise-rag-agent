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
HISTORY_FILE = "chat_history.json"
LOG_FILE = "chat_log.jsonl"

ALLOWED_READ_EXTENSIONS = {".py", ".md", ".txt", ".json", ".jsonl"}
EXCLUDED_READ_FILES = {".env", HISTORY_FILE, LOG_FILE, "todos.json"}
MAX_READ_LINES = 120
MAX_SEARCH_MATCHES = 20
MAX_PROJECT_SEARCH_MATCHES = 30

SYSTEM_MESSAGE = {
    "role": "system",
    "content": "You are a tiny AI agent. Use tools when they are useful.",
}
