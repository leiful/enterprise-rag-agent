# -*- coding: utf-8 -*-

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")


MODEL = os.environ.get("CHAT_MODEL", "").strip()
BASE_URL = os.environ.get("CHAT_BASE_URL", "").strip()
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
APP_USERNAME = os.environ.get("APP_USERNAME", "").strip()
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
SESSION_MAX_AGE_SECONDS = int(os.environ.get("SESSION_MAX_AGE_SECONDS", "604800"))
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").strip().lower() == "true"
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "lax").strip().lower()
LOGIN_MAX_FAILED_ATTEMPTS = int(os.environ.get("LOGIN_MAX_FAILED_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "300"))
CHAT_MAX_CONCURRENT_REQUESTS = int(os.environ.get("CHAT_MAX_CONCURRENT_REQUESTS", "20"))
CHAT_MAX_CONCURRENT_PER_USER = int(os.environ.get("CHAT_MAX_CONCURRENT_PER_USER", "1"))
CHAT_MAX_CONCURRENT_PER_CONVERSATION = int(os.environ.get("CHAT_MAX_CONCURRENT_PER_CONVERSATION", "1"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DATABASE_CONNECT_TIMEOUT_SECONDS = int(os.environ.get("DATABASE_CONNECT_TIMEOUT_SECONDS", "3"))
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "").strip()
EMBEDDING_BASE_URL = os.environ.get(
    "EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
).strip()
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-v4").strip()
MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19530").strip()
MILVUS_TOKEN = os.environ.get("MILVUS_TOKEN", "").strip()
MILVUS_COLLECTION = os.environ.get("MILVUS_COLLECTION", "ai_agent_vectors").strip()
RERANK_API_KEY = os.environ.get("RERANK_API_KEY", EMBEDDING_API_KEY).strip()
RERANK_API_URL = os.environ.get(
    "RERANK_API_URL",
    "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
).strip()
RERANK_MODEL = os.environ.get("RERANK_MODEL", "gte-rerank-v2").strip()
RERANK_MIN_SCORE = float(os.environ.get("RERANK_MIN_SCORE", "0.20"))
RERANK_MAX_CANDIDATES = int(os.environ.get("RERANK_MAX_CANDIDATES", "12"))

MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_TOKENS = int(os.environ.get("MAX_HISTORY_TOKENS", "8000"))
MAX_FILE_READ_LINES_PER_TURN = 120
LOG_FILE = "chat_log.jsonl"

ALLOWED_READ_EXTENSIONS = {".py", ".md", ".txt", ".json", ".jsonl"}
EXCLUDED_READ_FILES = {".env", LOG_FILE, "todos.json"}
MAX_READ_LINES = 120
MAX_SEARCH_MATCHES = 20
MAX_PROJECT_SEARCH_MATCHES = 30

# Retrieval performance settings
ENABLE_QUERY_REWRITE = os.environ.get("ENABLE_QUERY_REWRITE", "true").lower() == "true"
ENABLE_MULTI_QUERY = os.environ.get("ENABLE_MULTI_QUERY", "true").lower() == "true"
ENABLE_RERANK = os.environ.get("ENABLE_RERANK", "true").lower() == "true"
RERANK_MIN_CANDIDATES = int(os.environ.get("RERANK_MIN_CANDIDATES", "8"))
RECALL_K = int(os.environ.get("RECALL_K", "24"))
DEFAULT_KNOWLEDGE_TOP_K = int(os.environ.get("DEFAULT_KNOWLEDGE_TOP_K", "5"))
DEFAULT_KNOWLEDGE_MIN_SCORE = float(os.environ.get("DEFAULT_KNOWLEDGE_MIN_SCORE", "0.25"))
REQUIRE_DOCUMENT_DEPARTMENT = (
    os.environ.get("REQUIRE_DOCUMENT_DEPARTMENT", "true").strip().lower() == "true"
)
STRICT_KNOWLEDGE_ABSTENTION = (
    os.environ.get("STRICT_KNOWLEDGE_ABSTENTION", "true").strip().lower() == "true"
)
NO_EVIDENCE_ANSWER = "知识库中没有足够的相关证据支持回答这个问题。"
MIN_EVIDENCE_SOURCES = int(os.environ.get("MIN_EVIDENCE_SOURCES", "1"))
MULTI_QUERY_COUNT = int(os.environ.get("MULTI_QUERY_COUNT", "4"))
HYBRID_BM25_WEIGHT = float(os.environ.get("HYBRID_BM25_WEIGHT", "0.40"))
HYBRID_VECTOR_WEIGHT = float(os.environ.get("HYBRID_VECTOR_WEIGHT", "0.60"))
ENABLE_QUERY_COVERAGE_FILTER = (
    os.environ.get("ENABLE_QUERY_COVERAGE_FILTER", "true").strip().lower() == "true"
)
QUERY_COVERAGE_MIN = float(os.environ.get("QUERY_COVERAGE_MIN", "0.25"))
QUERY_CACHE_TTL_SECONDS = int(os.environ.get("QUERY_CACHE_TTL_SECONDS", "300"))
QUERY_CACHE_MAX_ENTRIES = int(os.environ.get("QUERY_CACHE_MAX_ENTRIES", "128"))
DEFAULT_CHUNK_SIZE = int(os.environ.get("DEFAULT_CHUNK_SIZE", "700"))
DEFAULT_CHUNK_OVERLAP = int(os.environ.get("DEFAULT_CHUNK_OVERLAP", "80"))
ENABLE_SEMANTIC_CHUNKING = os.environ.get("ENABLE_SEMANTIC_CHUNKING", "false").lower() == "true"
SEMANTIC_CHUNK_MIN_TEXT_LENGTH = int(os.environ.get("SEMANTIC_CHUNK_MIN_TEXT_LENGTH", "800"))
SEMANTIC_CHUNK_MIN_UNITS = int(os.environ.get("SEMANTIC_CHUNK_MIN_UNITS", "6"))
SEMANTIC_CHUNK_SOFT_RATIO = float(os.environ.get("SEMANTIC_CHUNK_SOFT_RATIO", "0.75"))
SEMANTIC_BOUNDARY_STD_FACTOR = float(os.environ.get("SEMANTIC_BOUNDARY_STD_FACTOR", "0.85"))
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))
DEFAULT_KNOWLEDGE_SOURCE_PATH = Path(
    os.environ.get("DEFAULT_KNOWLEDGE_SOURCE_PATH", str(PROJECT_ROOT / "knowledge_files"))
).resolve()
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).strip()
CORS_ALLOW_LOCALHOST_REGEX = (
    os.environ.get("CORS_ALLOW_LOCALHOST_REGEX", "true").strip().lower() == "true"
)


def _config_issue(name, severity, message):
    return {
        "name": name,
        "severity": severity,
        "message": message,
    }


def _nearest_existing_parent(path):
    current = path if path.is_dir() else path.parent
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _check_path_parent(path_value, name, label):
    if not path_value:
        return [_config_issue(name, "error", f"{label} is not configured.")]

    path = Path(path_value).expanduser()
    parent = _nearest_existing_parent(path)
    if not parent.exists():
        return [_config_issue(name, "error", f"{label} parent path does not exist: {path.parent}")]

    if not os.access(parent, os.W_OK):
        return [_config_issue(name, "error", f"{label} parent path is not writable: {parent}")]

    return []


def parse_csv_setting(value):
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def cors_allowed_origins():
    return parse_csv_setting(CORS_ALLOWED_ORIGINS)


def cors_allow_origin_regex():
    if CORS_ALLOW_LOCALHOST_REGEX:
        return r"http://(localhost|127\.0\.0\.1):517[0-9]"
    return None


def is_production():
    return APP_ENV == "production"


def validate_runtime_config():
    issues = []

    if APP_ENV not in {"development", "test", "staging", "production"}:
        issues.append(_config_issue(
            "APP_ENV",
            "error",
            "APP_ENV must be one of: development, test, staging, production.",
        ))

    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        issues.append(_config_issue(
            "DEEPSEEK_API_KEY",
            "error",
            "DeepSeek API key is missing; chat model startup will fail.",
        ))

    if not MODEL:
        issues.append(_config_issue(
            "CHAT_MODEL",
            "error",
            "CHAT_MODEL is not configured.",
        ))

    if not BASE_URL:
        issues.append(_config_issue(
            "CHAT_BASE_URL",
            "error",
            "CHAT_BASE_URL is not configured.",
        ))

    if not APP_USERNAME:
        issues.append(_config_issue("APP_USERNAME", "error", "Login username is not configured."))

    if not APP_PASSWORD:
        issues.append(_config_issue("APP_PASSWORD", "error", "Login password is not configured."))
    else:
        weak_passwords = {
            "123456",
            "password",
            "admin",
            "admin123",
            "change_this_local_password",
        }
        if APP_PASSWORD.lower() in weak_passwords:
            issues.append(_config_issue(
                "APP_PASSWORD",
                "warning",
                "Login password still looks like a default or weak password.",
            ))
        elif len(APP_PASSWORD) < 12:
            issues.append(_config_issue(
                "APP_PASSWORD",
                "warning",
                "Login password is shorter than 12 characters.",
            ))

    if not DATABASE_URL:
        issues.append(_config_issue(
            "DATABASE_URL",
            "error",
            "PostgreSQL DATABASE_URL is not configured.",
        ))

    if not EMBEDDING_API_KEY:
        issues.append(_config_issue(
            "EMBEDDING_API_KEY",
            "warning",
            "Embedding API key is missing; knowledge indexing and vector search will fail.",
        ))

    if EMBEDDING_DIM <= 0:
        issues.append(_config_issue(
            "EMBEDDING_DIM",
            "error",
            "EMBEDDING_DIM must be greater than 0.",
        ))

    if not MILVUS_URI:
        issues.append(_config_issue(
            "MILVUS_URI",
            "error",
            "MILVUS_URI is required for Milvus vector search.",
        ))

    if not MILVUS_COLLECTION:
        issues.append(_config_issue(
            "MILVUS_COLLECTION",
            "error",
            "MILVUS_COLLECTION is required for Milvus vector search.",
        ))

    issues.extend(_check_path_parent(
        str(DEFAULT_KNOWLEDGE_SOURCE_PATH),
        "DEFAULT_KNOWLEDGE_SOURCE_PATH",
        "Default knowledge source path",
    ))

    numeric_settings = {
        "SESSION_MAX_AGE_SECONDS": SESSION_MAX_AGE_SECONDS,
        "LOGIN_MAX_FAILED_ATTEMPTS": LOGIN_MAX_FAILED_ATTEMPTS,
        "LOGIN_LOCKOUT_SECONDS": LOGIN_LOCKOUT_SECONDS,
        "CHAT_MAX_CONCURRENT_REQUESTS": CHAT_MAX_CONCURRENT_REQUESTS,
        "CHAT_MAX_CONCURRENT_PER_USER": CHAT_MAX_CONCURRENT_PER_USER,
        "CHAT_MAX_CONCURRENT_PER_CONVERSATION": CHAT_MAX_CONCURRENT_PER_CONVERSATION,
        "DATABASE_CONNECT_TIMEOUT_SECONDS": DATABASE_CONNECT_TIMEOUT_SECONDS,
        "RECALL_K": RECALL_K,
        "DEFAULT_KNOWLEDGE_TOP_K": DEFAULT_KNOWLEDGE_TOP_K,
        "MIN_EVIDENCE_SOURCES": MIN_EVIDENCE_SOURCES,
        "MULTI_QUERY_COUNT": MULTI_QUERY_COUNT,
        "QUERY_CACHE_TTL_SECONDS": QUERY_CACHE_TTL_SECONDS,
        "QUERY_CACHE_MAX_ENTRIES": QUERY_CACHE_MAX_ENTRIES,
        "RERANK_MIN_CANDIDATES": RERANK_MIN_CANDIDATES,
        "RERANK_MAX_CANDIDATES": RERANK_MAX_CANDIDATES,
        "DEFAULT_CHUNK_SIZE": DEFAULT_CHUNK_SIZE,
    }
    for name, value in numeric_settings.items():
        if value <= 0:
            issues.append(_config_issue(name, "error", f"{name} must be greater than 0."))

    if DEFAULT_CHUNK_OVERLAP < 0:
        issues.append(_config_issue("DEFAULT_CHUNK_OVERLAP", "error", "DEFAULT_CHUNK_OVERLAP must not be negative."))
    elif DEFAULT_CHUNK_OVERLAP >= DEFAULT_CHUNK_SIZE:
        issues.append(_config_issue("DEFAULT_CHUNK_OVERLAP", "error", "DEFAULT_CHUNK_OVERLAP must be smaller than DEFAULT_CHUNK_SIZE."))

    if SEMANTIC_CHUNK_SOFT_RATIO <= 0 or SEMANTIC_CHUNK_SOFT_RATIO > 1:
        issues.append(_config_issue("SEMANTIC_CHUNK_SOFT_RATIO", "error", "SEMANTIC_CHUNK_SOFT_RATIO must be greater than 0 and no more than 1."))

    if SEMANTIC_BOUNDARY_STD_FACTOR < 0:
        issues.append(_config_issue("SEMANTIC_BOUNDARY_STD_FACTOR", "error", "SEMANTIC_BOUNDARY_STD_FACTOR must not be negative."))

    if RERANK_MIN_SCORE < 0:
        issues.append(_config_issue("RERANK_MIN_SCORE", "error", "RERANK_MIN_SCORE must not be negative."))

    if RERANK_MAX_CANDIDATES <= 0:
        issues.append(_config_issue("RERANK_MAX_CANDIDATES", "error", "RERANK_MAX_CANDIDATES must be greater than 0."))

    if DEFAULT_KNOWLEDGE_MIN_SCORE < 0:
        issues.append(_config_issue("DEFAULT_KNOWLEDGE_MIN_SCORE", "error", "DEFAULT_KNOWLEDGE_MIN_SCORE must not be negative."))

    if QUERY_COVERAGE_MIN < 0 or QUERY_COVERAGE_MIN > 1:
        issues.append(_config_issue("QUERY_COVERAGE_MIN", "error", "QUERY_COVERAGE_MIN must be between 0 and 1."))

    if MIN_EVIDENCE_SOURCES <= 0:
        issues.append(_config_issue("MIN_EVIDENCE_SOURCES", "error", "MIN_EVIDENCE_SOURCES must be greater than 0."))

    if HYBRID_BM25_WEIGHT < 0 or HYBRID_VECTOR_WEIGHT < 0:
        issues.append(_config_issue("HYBRID_WEIGHTS", "error", "Hybrid retrieval weights must not be negative."))
    elif HYBRID_BM25_WEIGHT + HYBRID_VECTOR_WEIGHT <= 0:
        issues.append(_config_issue("HYBRID_WEIGHTS", "error", "At least one hybrid retrieval weight must be greater than 0."))

    if SESSION_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
        issues.append(_config_issue(
            "SESSION_COOKIE_SAMESITE",
            "error",
            "SESSION_COOKIE_SAMESITE must be one of: lax, strict, none.",
        ))
    elif SESSION_COOKIE_SAMESITE == "none" and not SESSION_COOKIE_SECURE:
        issues.append(_config_issue(
            "SESSION_COOKIE_SECURE",
            "error",
            "SESSION_COOKIE_SECURE must be true when SESSION_COOKIE_SAMESITE is none.",
        ))

    origins = cors_allowed_origins()
    if not origins and not CORS_ALLOW_LOCALHOST_REGEX:
        issues.append(_config_issue(
            "CORS_ALLOWED_ORIGINS",
            "error",
            "At least one CORS origin or localhost regex support must be configured.",
        ))

    if any(origin == "*" for origin in origins):
        severity = "error" if is_production() else "warning"
        issues.append(_config_issue(
            "CORS_ALLOWED_ORIGINS",
            severity,
            "Wildcard CORS origins are not safe with credentialed browser sessions.",
        ))

    if is_production():
        if not SESSION_COOKIE_SECURE:
            issues.append(_config_issue(
                "SESSION_COOKIE_SECURE",
                "error",
                "SESSION_COOKIE_SECURE must be true in production.",
            ))
        if SESSION_COOKIE_SAMESITE == "none" and not SESSION_COOKIE_SECURE:
            issues.append(_config_issue(
                "SESSION_COOKIE_SECURE",
                "error",
                "Cross-site production cookies require SESSION_COOKIE_SECURE=true.",
            ))
        if CORS_ALLOW_LOCALHOST_REGEX:
            issues.append(_config_issue(
                "CORS_ALLOW_LOCALHOST_REGEX",
                "warning",
                "Disable localhost CORS regex in production unless this deployment is local-only.",
            ))
        localhost_origins = [
            origin for origin in origins
            if origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")
        ]
        if localhost_origins:
            issues.append(_config_issue(
                "CORS_ALLOWED_ORIGINS",
                "warning",
                "Production CORS origins still include localhost entries.",
            ))

    return issues

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "You are a project assistant inside a private web console. "
        "Answer the user's question directly in Chinese when the user writes Chinese. "
        "Use tools only when they are necessary for the user's request. "
        "Every user message includes a Knowledge base preflight result before the user question. "
        "Use that preflight first: if it says no supported knowledge evidence was found, begin by saying the knowledge base does not contain enough relevant evidence, then answer with general knowledge when appropriate. "
        "If the preflight contains snippets, first check whether they are actually about the user's question. If they are unrelated or insufficient, say the knowledge base does not contain enough relevant evidence. "
        "If the snippets are relevant, explicitly tell the user that the answer is based on the knowledge base materials before giving the substantive answer. "
        "Only cite the provided source labels such as [K1] for claims directly supported by the matching snippet. "
        "Do not add unsupported details from general knowledge when a knowledge-base answer is requested. "
        "Do not inspect project files just because the user asks a casual identity question like 'who am I'. "
        "For that, answer that they are the signed-in user you are chatting with, and explain that you do not know more personal identity unless the app provides it."
    ),
}
