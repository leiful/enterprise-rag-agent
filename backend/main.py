# -*- coding: utf-8 -*-

from contextlib import asynccontextmanager
import base64
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app_logging import configure_logging, get_logger, log_event, new_request_id, reset_request_id, set_request_id
from AI_agent import build_knowledge_preflight, create_client, run_agent, run_agent_stream, search_knowledge_payload
from config import (
    APP_PASSWORD,
    APP_USERNAME,
    BASE_URL,
    CHAT_MAX_CONCURRENT_PER_CONVERSATION,
    CHAT_MAX_CONCURRENT_PER_USER,
    CHAT_MAX_CONCURRENT_REQUESTS,
    cors_allowed_origins,
    cors_allow_origin_regex,
    DEFAULT_KNOWLEDGE_MIN_SCORE,
    DEFAULT_KNOWLEDGE_TOP_K,
    ENABLE_MULTI_QUERY,
    ENABLE_QUERY_REWRITE,
    ENABLE_RERANK,
    MIN_EVIDENCE_SOURCES,
    LOGIN_LOCKOUT_SECONDS,
    LOGIN_MAX_FAILED_ATTEMPTS,
    RECALL_K,
    REQUIRE_DOCUMENT_DEPARTMENT,
    STRICT_KNOWLEDGE_ABSTENTION,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE_SECONDS,
)
from config import SYSTEM_MESSAGE
from config import validate_runtime_config
from database import (
    authenticate_user,
    add_admin_audit_event,
    add_knowledge_access_audit,
    add_rag_feedback,
    connect,
    count_admin_audit_events,
    count_knowledge_access_audit,
    create_department,
    create_index_job,
    create_conversation,
    create_session as save_session,
    create_user,
    delete_department,
    delete_missing_knowledge_source_files,
    delete_session,
    department_names,
    find_feedback_message_id,
    get_conversation,
    get_bm25_stats,
    get_index_job,
    get_index_job_status_counts,
    get_knowledge_source_file_status_counts,
    get_session,
    list_admin_audit_events,
    list_knowledge_access_audit,
    list_rag_feedback,
    list_departments,
    init_db,
    list_conversations,
    list_users,
    list_messages,
    save_chat_turn,
    reassign_knowledge_source_files,
    summarize_rag_feedback,
    update_index_job,
    update_knowledge_source_file_by_job,
    update_user,
)
import knowledge
import knowledge_sources
import tools
import vector_store

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rag_eval as rag_eval_script


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    authenticated: bool
    username: str | None = None
    role: str | None = None
    departments: list[str] = Field(default_factory=list)


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "user"
    departments: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    role: str = "user"
    departments: list[str] = Field(default_factory=list)


class DepartmentCreateRequest(BaseModel):
    name: str


class RagEvalRunRequest(BaseModel):
    suite: str = "core"
    skip_chat: bool = False
    skip_upload: bool = False


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    departments: list[str] = Field(default_factory=list)
    created_at: str


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    answer: str
    conversation_id: int
    sources: list[dict] = Field(default_factory=list)


class ConversationRequest(BaseModel):
    title: str | None = None


class IndexFileRequest(BaseModel):
    path: str
    document_id: str | None = None
    notes: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    metadata: dict | None = None


class SearchKnowledgeRequest(BaseModel):
    query: str
    top_k: int = DEFAULT_KNOWLEDGE_TOP_K
    min_score: float = DEFAULT_KNOWLEDGE_MIN_SCORE
    category: str | None = None
    tags: list[str] | None = None
    file_extensions: list[str] | None = None


class FeedbackRequest(BaseModel):
    feedback_type: str
    conversation_id: int | None = None
    message_id: int | None = None
    comment: str | None = None
    query: str | None = None
    answer: str | None = None
    sources: list[dict] = Field(default_factory=list)


class KnowledgeAuditResponse(BaseModel):
    id: int
    user_id: int | None = None
    username: str
    action: str
    query: str
    source_count: int
    sources: list[dict] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    created_at: str


class IndexJobResponse(BaseModel):
    job_id: str
    status: str
    document_id: str | None = None
    path: str | None = None
    result: dict | None = None
    error: str | None = None


class BalanceInfo(BaseModel):
    currency: str
    total_balance: str
    granted_balance: str
    topped_up_balance: str


class DeepSeekBalanceResponse(BaseModel):
    is_available: bool
    balance_infos: list[BalanceInfo]


client = None
startup_error = None
config_issues = []
SESSION_COOKIE = "agent_session"
login_failures = {}
logger = get_logger("backend.main")
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


def startup():
    global client, startup_error, config_issues
    configure_logging()
    config_issues = validate_runtime_config()
    init_db()
    knowledge_sources.ensure_default_local_source()

    try:
        client = create_client()
        startup_error = None
        log_event(
            logger,
            20,
            "app_startup_completed",
            config_error_count=sum(1 for issue in config_issues if issue["severity"] == "error"),
            config_warning_count=sum(1 for issue in config_issues if issue["severity"] == "warning"),
        )
    except RuntimeError as error:
        startup_error = str(error)
        log_event(
            logger,
            40,
            "app_startup_model_client_failed",
            error=str(error),
            config_error_count=sum(1 for issue in config_issues if issue["severity"] == "error"),
            config_warning_count=sum(1 for issue in config_issues if issue["severity"] == "warning"),
        )


@asynccontextmanager
async def lifespan(app):
    startup()
    yield


def require_auth_config():
    if not APP_USERNAME or not APP_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login is not configured.",
        )


def create_session(user_id):
    session_id = secrets.token_urlsafe(32)
    save_session(session_id, user_id, time.time() + SESSION_MAX_AGE_SECONDS)
    return session_id


def get_session_username(session_id):
    require_auth_config()

    session = get_session(session_id, time.time())
    if not session:
        return None

    return {
        "id": session["user_id"],
        "username": session["username"],
        "role": session["role"],
        "departments": session.get("departments") or [],
    }


def require_user(agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if not agent_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login required.",
        )

    user = get_session_username(agent_session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session.",
        )

    return user


def require_admin(user=Depends(require_user)):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required.",
        )
    return user


def user_knowledge_departments(user):
    if user.get("role") == "admin":
        return None
    return user.get("departments") or []


def get_client_ip(request: Request):
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def login_failure_key(request: Request, username: str):
    return (get_client_ip(request), username.strip().lower())


def clear_expired_login_failures(now):
    expired_keys = [
        key for key, value in login_failures.items()
        if value.get("locked_until", 0) <= now and value.get("failed_count", 0) <= 0
    ]
    for key in expired_keys:
        login_failures.pop(key, None)


def is_login_locked(key, now):
    record = login_failures.get(key)
    if not record:
        return False
    locked_until = record.get("locked_until", 0)
    if locked_until > now:
        return True
    if locked_until:
        login_failures.pop(key, None)
    return False


def record_login_failure(key, *, username, client_ip):
    now = time.time()
    record = login_failures.get(key, {"failed_count": 0, "locked_until": 0})
    failed_count = record.get("failed_count", 0) + 1
    locked_until = 0
    if failed_count >= LOGIN_MAX_FAILED_ATTEMPTS:
        locked_until = now + LOGIN_LOCKOUT_SECONDS
        failed_count = 0
        log_event(
            logger,
            30,
            "login_lockout_started",
            username=username,
            client_ip=client_ip,
            lockout_seconds=LOGIN_LOCKOUT_SECONDS,
        )
    login_failures[key] = {
        "failed_count": failed_count,
        "locked_until": locked_until,
    }


def clear_login_failures(key):
    login_failures.pop(key, None)


def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")


app = FastAPI(title="AI Tool Calling Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_origin_regex=cors_allow_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-Id", "X-Knowledge-Sources"],
)


@app.middleware("http")
async def request_logging_middleware(request, call_next):
    request_id = request.headers.get("X-Request-Id") or new_request_id()
    token = set_request_id(request_id)
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-Id"] = request_id
        add_security_headers(response)
        return response
    except Exception as error:
        log_event(
            logger,
            40,
            "http_request_failed",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            error=str(error),
        )
        raise
    finally:
        log_event(
            logger,
            20,
            "http_request_completed",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        reset_request_id(token)


@app.get("/health")
def health():
    has_config_errors = any(issue["severity"] == "error" for issue in config_issues)
    has_config_warnings = any(issue["severity"] == "warning" for issue in config_issues)
    database_health = get_database_health()
    model_status = "ok" if startup_error is None else "error"
    config_status = "error" if has_config_errors else "warning" if has_config_warnings else "ok"
    overall_status = "ok"
    if startup_error is not None or has_config_errors or database_health["status"] == "error":
        overall_status = "error"
    elif has_config_warnings:
        overall_status = "degraded"

    return {
        "status": overall_status,
        "error": startup_error,
        "checks": {
            "config": {
                "status": config_status,
                "issues": config_issues,
            },
            "database": database_health,
            "model_client": {
                "status": model_status,
                "error": startup_error,
            },
        },
    }


@app.get("/admin/rag/status", dependencies=[Depends(require_admin)])
def admin_rag_status():
    return get_rag_operational_status()


@app.get("/admin/rag/eval", dependencies=[Depends(require_admin)])
def admin_rag_eval():
    return latest_rag_eval_report()


@app.get("/admin/rag/eval/suites", dependencies=[Depends(require_admin)])
def admin_rag_eval_suites():
    return {"suites": rag_eval_suite_list()}


@app.post("/admin/rag/eval/run", dependencies=[Depends(require_admin)])
def admin_run_rag_eval(request_data: RagEvalRunRequest, user=Depends(require_admin)):
    try:
        result = run_rag_eval_suite(
            request_data.suite,
            skip_chat=request_data.skip_chat,
            skip_upload=request_data.skip_upload,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error))

    add_admin_audit_event(
        user,
        "rag_eval.run",
        "rag_eval",
        target_id=request_data.suite,
        details=result,
    )
    return result


@app.get("/admin/feedback", dependencies=[Depends(require_admin)])
def admin_feedback(limit: int = 100):
    return {
        "summary": summarize_rag_feedback(),
        "feedback": list_rag_feedback(limit),
    }


@app.post("/login", response_model=AuthResponse)
def login(request_data: LoginRequest, response: Response, request: Request):
    require_auth_config()

    now = time.time()
    clear_expired_login_failures(now)
    client_ip = get_client_ip(request)
    failure_key = login_failure_key(request, request_data.username)
    if is_login_locked(failure_key, now):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(LOGIN_LOCKOUT_SECONDS)},
        )

    user = authenticate_user(request_data.username, request_data.password)
    if not user:
        record_login_failure(
            failure_key,
            username=request_data.username,
            client_ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    clear_login_failures(failure_key)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session(user["id"]),
        httponly=True,
        max_age=SESSION_MAX_AGE_SECONDS,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE,
    )
    return AuthResponse(
        authenticated=True,
        username=user["username"],
        role=user["role"],
        departments=user.get("departments") or [],
    )


@app.post("/logout", response_model=AuthResponse)
def logout(response: Response, agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if agent_session:
        delete_session(agent_session)

    response.delete_cookie(
        key=SESSION_COOKIE,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE,
    )
    return AuthResponse(authenticated=False)


@app.get("/me", response_model=AuthResponse)
def me(agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if not agent_session:
        return AuthResponse(authenticated=False)

    user = get_session_username(agent_session)
    if user is None:
        return AuthResponse(authenticated=False)

    return AuthResponse(
        authenticated=True,
        username=user["username"],
        role=user["role"],
        departments=user.get("departments") or [],
    )


@app.get("/admin/users", dependencies=[Depends(require_admin)])
def admin_list_users():
    return {"users": list_users()}


@app.get("/admin/departments", dependencies=[Depends(require_admin)])
def admin_list_departments():
    return {"departments": list_departments()}


@app.post("/admin/departments", dependencies=[Depends(require_admin)])
def admin_create_department(request_data: DepartmentCreateRequest, user=Depends(require_admin)):
    try:
        department = create_department(request_data.name)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    except Exception as error:
        if "unique" in str(error).lower() or "duplicate" in str(error).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Department already exists.",
            )
        raise
    add_admin_audit_event(
        user,
        "department.create",
        "department",
        target_id=department["id"],
        details={"name": department["name"]},
    )
    return {"department": department}


@app.delete("/admin/departments/{department_id}", dependencies=[Depends(require_admin)])
def admin_delete_department(department_id: int, user=Depends(require_admin)):
    if not delete_department(department_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found.",
        )
    add_admin_audit_event(
        user,
        "department.delete",
        "department",
        target_id=department_id,
    )
    return {"deleted": True}


@app.post("/admin/users", response_model=UserResponse, dependencies=[Depends(require_admin)])
def admin_create_user(request_data: UserCreateRequest, user=Depends(require_admin)):
    if request_data.role not in {"admin", "user"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin' or 'user'.",
        )
    if len(request_data.password) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 12 characters.",
        )
    if request_data.role == "user" and not request_data.departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department is required for user accounts.",
        )
    configured_departments = {department.lower() for department in department_names()}
    unknown_departments = [
        department for department in request_data.departments
        if department.lower() not in configured_departments
    ]
    if unknown_departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown department: {', '.join(unknown_departments)}.",
        )

    try:
        user = create_user(
            request_data.username,
            request_data.password,
            request_data.role,
            departments=request_data.departments,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    except Exception as error:
        if "unique" in str(error).lower() or "duplicate" in str(error).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists.",
            )
        raise

    add_admin_audit_event(
        user,
        "user.create",
        "user",
        target_id=user["id"],
        details={
            "username": user["username"],
            "role": user["role"],
            "departments": user.get("departments") or [],
        },
    )
    return UserResponse(**user)


@app.patch("/admin/users/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
def admin_update_user(user_id: int, request_data: UserUpdateRequest, user=Depends(require_admin)):
    if request_data.role not in {"admin", "user"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin' or 'user'.",
        )
    departments = [] if request_data.role == "admin" else request_data.departments
    if request_data.role == "user" and not departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department is required for user accounts.",
        )
    configured_departments = {department.lower() for department in department_names()}
    unknown_departments = [
        department for department in departments
        if department.lower() not in configured_departments
    ]
    if unknown_departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown department: {', '.join(unknown_departments)}.",
        )

    updated = update_user(user_id, role=request_data.role, departments=departments)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    add_admin_audit_event(
        user,
        "user.update",
        "user",
        target_id=updated["id"],
        details={
            "username": updated["username"],
            "role": updated["role"],
            "departments": updated.get("departments") or [],
        },
    )
    return UserResponse(**updated)


def make_conversation_title(message):
    title = " ".join(message.split())
    if len(title) > 48:
        return f"{title[:45]}..."
    return title or "New conversation"


def build_agent_messages(saved_messages):
    messages = [SYSTEM_MESSAGE.copy()]
    for message in saved_messages:
        if message["role"] in {"user", "assistant"}:
            messages.append({
                "role": message["role"],
                "content": message["content"],
            })
    return messages


def encode_sources_header(sources):
    sources_json = json.dumps(sources or [], ensure_ascii=False)
    return base64.b64encode(sources_json.encode("utf-8")).decode("ascii")


def document_ocr_available():
    return importlib.util.find_spec("pytesseract") is not None


def answer_abstained(answer):
    normalized = (answer or "").lower()
    abstention_phrases = (
        "没有足够",
        "相关证据",
        "无法根据知识库",
        "知识库中没有",
        "does not contain enough",
        "not enough evidence",
        "insufficient evidence",
        "no supported knowledge evidence",
    )
    return any(phrase in normalized for phrase in abstention_phrases)


RAG_EVAL_SUITES = {
    "core": {
        "id": "core",
        "name": "Core Regression",
        "description": "20 local questions for retrieval, citations, distractors, and no-evidence behavior.",
        "docs_dir": Path(__file__).resolve().parents[1] / "rag_eval" / "sample_docs",
        "questions": Path(__file__).resolve().parents[1] / "rag_eval" / "questions.json",
        "top_k": 3,
        "min_score": 0.3,
    },
    "acceptance": {
        "id": "acceptance",
        "name": "Acceptance",
        "description": "12 practical acceptance questions for human-facing answer quality.",
        "docs_dir": Path(__file__).resolve().parents[1] / "rag_eval" / "sample_docs",
        "questions": Path(__file__).resolve().parents[1] / "rag_eval" / "manual_questions.json",
        "top_k": 5,
        "min_score": 0.25,
    },
    "ragbench": {
        "id": "ragbench",
        "name": "RAGBench Sample",
        "description": "5 converted public-benchmark-style eManual questions.",
        "docs_dir": Path(__file__).resolve().parents[1] / "rag_eval" / "generated" / "ragbench_emanual" / "docs",
        "questions": Path(__file__).resolve().parents[1] / "rag_eval" / "generated" / "ragbench_emanual" / "questions.json",
        "top_k": 3,
        "min_score": 0.3,
    },
}


def rag_eval_suite_list():
    suites = []
    for suite in RAG_EVAL_SUITES.values():
        question_count = 0
        if suite["questions"].exists():
            try:
                question_count = len(json.loads(suite["questions"].read_text(encoding="utf-8")))
            except Exception:
                question_count = 0
        suites.append({
            "id": suite["id"],
            "name": suite["name"],
            "description": suite["description"],
            "question_count": question_count,
        })
    return suites


def index_rag_eval_docs(docs_dir):
    indexed = []
    for path in sorted(docs_dir.glob("*")):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        relative_path = str(path.relative_to(Path(__file__).resolve().parents[1]))
        result, error = knowledge.index_file(
            relative_path,
            document_id=path.name,
            notes="rag_eval sample document",
            force_reindex=True,
            use_original_name=True,
        )
        if error:
            raise RuntimeError(f"Failed to index {path.name}: {error}")
        indexed.append(result)
    return indexed


def run_rag_eval_suite(suite_id, *, skip_chat=False, skip_upload=False):
    suite = RAG_EVAL_SUITES.get(suite_id)
    if not suite:
        raise ValueError(f"Unknown evaluation suite: {suite_id}")
    if not suite["questions"].exists():
        raise FileNotFoundError(f"Questions file not found: {suite['questions']}")
    if not suite["docs_dir"].exists():
        raise FileNotFoundError(f"Docs directory not found: {suite['docs_dir']}")

    if not skip_upload:
        index_rag_eval_docs(suite["docs_dir"])

    questions = rag_eval_script.load_json(suite["questions"])
    def search_callback(query, top_k, min_score):
        return search_knowledge_payload(
            query,
            top_k=top_k,
            min_score=min_score,
            client=client,
        )

    def chat_callback(message, conversation_id=None):
        messages = [SYSTEM_MESSAGE.copy()]
        knowledge_preflight = build_knowledge_preflight(message, client=client, messages=messages)
        result = run_agent(
            client,
            messages,
            message,
            knowledge_preflight=knowledge_preflight,
            return_sources=True,
        )
        if isinstance(result, dict):
            return {
                "answer": result.get("answer", ""),
                "sources": result.get("sources") or knowledge_preflight.get("sources") or [],
                "conversation_id": conversation_id,
            }
        return {
            "answer": str(result),
            "sources": knowledge_preflight.get("sources") or [],
            "conversation_id": conversation_id,
        }

    rows = rag_eval_script.run_questions(
        rag_eval_script.LocalApiClient(
            search_callback=search_callback,
            chat_callback=None if skip_chat else chat_callback,
        ),
        questions,
        suite["top_k"],
        suite["min_score"],
        skip_chat,
    )
    json_path, csv_path, md_path, summary = rag_eval_script.write_reports(
        rows,
        Path(__file__).resolve().parents[1] / "rag_eval" / "reports",
        suite_id=suite["id"],
    )
    return {
        "suite": {
            "id": suite["id"],
            "name": suite["name"],
            "question_count": len(questions),
        },
        "report": {
            "name": json_path.name,
            "path": str(json_path),
            "csv_path": str(csv_path),
            "md_path": str(md_path),
        },
        "summary": summary,
    }


def latest_rag_eval_report():
    reports_dir = Path(__file__).resolve().parents[1] / "rag_eval" / "reports"
    report_paths = sorted(
        {
            *reports_dir.glob("rag_eval_*.json"),
            *reports_dir.glob("manual_eval_*.json"),
        },
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not report_paths:
        return {
            "available": False,
            "report": None,
            "summary": {},
            "rows": [],
        }

    report_path = report_paths[0]
    try:
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as error:
        return {
            "available": False,
            "report": {"path": str(report_path), "error": str(error)},
            "summary": {},
            "rows": [],
        }

    if isinstance(report_data, dict) and "results" in report_data:
        raw_rows = report_data.get("results") or []
        manual_summary = report_data.get("summary") or {}
        rows = []
        for row in raw_rows:
            normalized = dict(row)
            expected_docs = normalized.get("expected_docs") or []
            top_document = normalized.get("top_document") or normalized.get("k1_document")
            score = normalized.get("score")
            try:
                numeric_score = float(score)
            except (TypeError, ValueError):
                numeric_score = None

            if "expected_hit" not in normalized:
                normalized["expected_hit"] = bool(normalized.get("expected_doc_hit"))
            if "top_document" not in normalized:
                normalized["top_document"] = top_document
            if "top_score" not in normalized:
                normalized["top_score"] = score
            if normalized.get("answer") and answer_abstained(normalized.get("answer")):
                normalized["abstained"] = True
            if "top1_hit" not in normalized:
                normalized["top1_hit"] = bool(top_document and top_document in expected_docs)
            if "unexpected_sources" not in normalized and normalized.get("should_abstain"):
                normalized["unexpected_sources"] = not bool(normalized.get("abstained"))
            if "strict_failure" not in normalized:
                normalized["strict_failure"] = (
                    numeric_score is not None
                    and numeric_score < 7
                    and not (
                        normalized.get("should_abstain")
                        and normalized.get("abstained")
                        and not normalized.get("source_documents")
                    )
                )
            if normalized.get("strict_failure") and not normalized.get("failure_reasons"):
                normalized["failure_reasons"] = ["manual_score_below_7"]
            rows.append(normalized)
    else:
        manual_summary = {}
        rows = report_data

    answerable_rows = [row for row in rows if row.get("expected_docs")]
    unknown_rows = [row for row in rows if not row.get("expected_docs")]
    citation_rows = [row for row in rows if row.get("answer")]
    expected_hits = sum(1 for row in answerable_rows if row.get("expected_hit"))
    top1_hits = sum(1 for row in answerable_rows if row.get("top1_hit"))
    reciprocal_rank_total = 0
    for row in answerable_rows:
        try:
            if row.get("expected_rank"):
                reciprocal_rank_total += 1 / int(row["expected_rank"])
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    unexpected_sources = sum(1 for row in unknown_rows if row.get("unexpected_sources"))
    abstention_correct = sum(
        1 for row in unknown_rows
        if row.get("abstained") and not row.get("source_documents")
    )
    missing_citations = sum(
        1 for row in answerable_rows
        if row.get("answer") and not row.get("answer_has_citation")
    )
    strict_failures = sum(1 for row in rows if row.get("strict_failure"))
    failure_reasons = {}
    for row in rows:
        for reason in row.get("failure_reasons") or []:
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    failed_rows = [
        row for row in rows
        if (row.get("expected_docs") and not row.get("expected_hit"))
        or row.get("unexpected_sources")
        or row.get("strict_failure")
    ]
    mtime = datetime.fromtimestamp(report_path.stat().st_mtime, timezone.utc).isoformat()
    return {
        "available": True,
        "report": {
            "name": report_path.name,
            "path": str(report_path),
            "updated_at": mtime,
        },
        "summary": {
            "total": len(rows),
            "answerable": len(answerable_rows),
            "expected_hits": expected_hits,
            "recall_at_k": expected_hits / len(answerable_rows) if answerable_rows else 0,
            "top1_hit_rate": top1_hits / len(answerable_rows) if answerable_rows else 0,
            "mrr": reciprocal_rank_total / len(answerable_rows) if answerable_rows else 0,
            "citation_rate": (
                sum(1 for row in citation_rows if row.get("answer_has_citation")) / len(citation_rows)
                if citation_rows else 0
            ),
            "abstention_accuracy": (
                abstention_correct / len(unknown_rows)
                if unknown_rows else 0
            ),
            "unexpected_sources": unexpected_sources,
            "missing_citations": missing_citations,
            "strict_failures": strict_failures,
            "failure_reasons": failure_reasons,
            "unknown": len(unknown_rows),
            "failed_count": len(failed_rows),
            "average_score": manual_summary.get("average_score"),
        },
        "rows": rows[:100],
        "failed_rows": failed_rows[:20],
    }


def search_result_to_source(result):
    metadata = result.metadata or {}
    return {
        "score": result.score,
        "chunk_id": result.chunk_id,
        "document_id": result.document_id,
        "chunk_index": result.chunk_index,
        "metadata": metadata,
        "page_start": metadata.get("page_start"),
        "page_end": metadata.get("page_end"),
        "text": result.text,
    }


def parse_tags_field(tags: str | None):
    if not tags:
        return None
    try:
        return json.loads(tags)
    except Exception:
        return [tag.strip() for tag in tags.split(",") if tag.strip()]


def parse_metadata_field(metadata: str | None):
    if not metadata:
        return None
    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError as error:
        raise ValueError(f"metadata must be valid JSON: {error.msg}")
    if not isinstance(parsed, dict):
        raise ValueError("metadata must be a JSON object")
    return parsed


def run_index_job(
    job_id: str,
    path: str,
    document_id: str | None,
    notes: str | None,
    category: str | None,
    tags: list[str] | None,
    metadata: dict | None,
    use_original_name: bool,
    force_reindex: bool = False,
):
    update_index_job(job_id, status="running")
    start = time.perf_counter()
    log_event(
        logger,
        20,
        "knowledge_index_job_started",
        job_id=job_id,
        document_id=document_id,
        path=path,
        category=category,
        tags=tags or [],
        metadata=metadata or {},
    )
    try:
        result, error = knowledge.index_file(
            path,
            document_id,
            notes=notes,
            category=category,
            tags=tags,
            metadata=metadata,
            force_reindex=force_reindex,
            use_original_name=use_original_name,
        )
        if error:
            update_index_job(job_id, status="failed", error=error)
            update_knowledge_source_file_by_job(job_id, "failed")
            log_event(
                logger,
                40,
                "knowledge_index_job_failed",
                job_id=job_id,
                document_id=document_id,
                path=path,
                error=error,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            return
        update_index_job(
            job_id,
            status="completed",
            document_id=result.get("document_id"),
            path=result.get("path"),
            result=result,
            error=None,
        )
        update_knowledge_source_file_by_job(job_id, "indexed")
        log_event(
            logger,
            20,
            "knowledge_index_job_completed",
            job_id=job_id,
            document_id=result.get("document_id"),
            path=result.get("path"),
            chunk_count=result.get("chunk_count"),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
    except Exception as error:
        update_index_job(job_id, status="failed", error=str(error))
        update_knowledge_source_file_by_job(job_id, "failed")
        log_event(
            logger,
            40,
            "knowledge_index_job_exception",
            job_id=job_id,
            document_id=document_id,
            path=path,
            error=str(error),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )


def enqueue_index_job(
    background_tasks: BackgroundTasks,
    *,
    path: str,
    document_id: str | None,
    notes: str | None,
    category: str | None,
    tags: list[str] | None,
    use_original_name: bool,
    metadata: dict | None = None,
    force_reindex: bool = False,
):
    job_id = secrets.token_urlsafe(16)
    create_index_job(job_id, document_id=document_id, path=path, status="queued")
    background_tasks.add_task(
        run_index_job,
        job_id,
        path,
        document_id,
        notes,
        category,
        tags,
        metadata,
        use_original_name,
        force_reindex,
    )
    return job_id


def get_database_health():
    try:
        with connect() as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as error:
        return {
            "status": "error",
            "error": str(error),
        }
    return {"status": "ok"}


def get_rag_operational_status():
    documents = vector_store.list_documents()
    total_chunks = sum(int(document.get("chunk_count") or 0) for document in documents)
    sources = knowledge_sources.list_sources()
    source_file_status_counts = get_knowledge_source_file_status_counts()
    index_job_status_counts = get_index_job_status_counts()
    bm25_stats = get_bm25_stats()
    eval_report = latest_rag_eval_report()
    feedback_summary = summarize_rag_feedback()

    enabled_unsynced_sources = [
        source for source in sources
        if source.get("enabled") and not source.get("last_sync_at")
    ]
    failed_index_jobs = index_job_status_counts.get("failed", 0)
    missing_source_files = source_file_status_counts.get("missing", 0)

    rag_status = "ok"
    issues = []
    if failed_index_jobs:
        rag_status = "degraded"
        issues.append({
            "name": "failed_index_jobs",
            "severity": "warning",
            "message": f"{failed_index_jobs} knowledge index job(s) failed.",
        })
    if missing_source_files:
        rag_status = "degraded"
        issues.append({
            "name": "missing_source_files",
            "severity": "warning",
            "message": f"{missing_source_files} source file(s) are missing and no longer indexed.",
        })
    if enabled_unsynced_sources:
        rag_status = "degraded"
        issues.append({
            "name": "unsynced_sources",
            "severity": "warning",
            "message": f"{len(enabled_unsynced_sources)} enabled knowledge source(s) have not completed a sync.",
        })
    if eval_report.get("available") and eval_report.get("summary", {}).get("failed_count"):
        rag_status = "degraded"
        issues.append({
            "name": "rag_eval_failures",
            "severity": "warning",
            "message": f"{eval_report['summary']['failed_count']} RAG evaluation row(s) need review.",
        })

    return {
        "status": rag_status,
        "issues": issues,
        "documents": {
            "count": len(documents),
            "chunk_count": total_chunks,
        },
        "sources": {
            "count": len(sources),
            "enabled_count": sum(1 for source in sources if source.get("enabled")),
            "file_status_counts": source_file_status_counts,
        },
        "index_jobs": {
            "status_counts": index_job_status_counts,
        },
        "retrieval": {
            "vector_store_backend": vector_store.VECTOR_STORE_BACKEND,
            "chroma_collection": vector_store.CHROMA_COLLECTION_NAME,
            "bm25_total_docs": bm25_stats.get("total_docs", 0),
            "bm25_avg_doc_len": bm25_stats.get("avg_doc_len", 0.0),
            "query_rewrite_enabled": ENABLE_QUERY_REWRITE,
            "multi_query_enabled": ENABLE_MULTI_QUERY,
            "rerank_enabled": ENABLE_RERANK,
            "recall_k": RECALL_K,
            "default_top_k": DEFAULT_KNOWLEDGE_TOP_K,
            "default_min_score": DEFAULT_KNOWLEDGE_MIN_SCORE,
            "min_evidence_sources": MIN_EVIDENCE_SOURCES,
            "strict_abstention_enabled": STRICT_KNOWLEDGE_ABSTENTION,
            "require_document_department": REQUIRE_DOCUMENT_DEPARTMENT,
        },
        "chat_admission": current_chat_admission_status(),
        "quality": {
            "latest_eval": eval_report.get("summary", {}) if eval_report.get("available") else {},
        },
        "parsing": {
            "supported_extensions": sorted(knowledge.ALLOWED_KNOWLEDGE_EXTENSIONS),
            "ocr_available": document_ocr_available(),
            "ocr_note": "Scanned PDFs and image-only files require OCR support before indexing text.",
        },
        "audit": {
            "event_count": count_knowledge_access_audit(),
            "admin_event_count": count_admin_audit_events(),
        },
        "feedback": feedback_summary,
    }


def get_deepseek_balance():
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEEPSEEK_API_KEY is not configured.",
        )

    request = UrlRequest(
        f"{BASE_URL.rstrip('/')}/user/balance",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek balance request failed with status {error.code}.",
        )
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek balance request failed: {error}",
        )


@app.get("/conversations", dependencies=[Depends(require_user)])
def conversations(user=Depends(require_user)):
    return {"conversations": list_conversations(user["id"])}


@app.post("/conversations", dependencies=[Depends(require_user)])
def new_conversation(request: ConversationRequest, user=Depends(require_user)):
    title = request.title or "New conversation"
    conversation_id = create_conversation(user["id"], title)
    return {
        "id": conversation_id,
        "title": title,
    }


@app.get("/conversations/{conversation_id}/messages", dependencies=[Depends(require_user)])
def conversation_messages(conversation_id: int, user=Depends(require_user)):
    conversation = get_conversation(user["id"], conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return {
        "conversation": conversation,
        "messages": list_messages(user["id"], conversation_id),
    }


@app.post("/feedback", dependencies=[Depends(require_user)])
def create_feedback(request: FeedbackRequest, user=Depends(require_user)):
    if request.conversation_id is not None and not get_conversation(user["id"], request.conversation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    message_id = request.message_id or find_feedback_message_id(
        user["id"],
        request.conversation_id,
        request.answer,
    )
    try:
        feedback_id = add_rag_feedback(
            user,
            request.feedback_type,
            conversation_id=request.conversation_id,
            message_id=message_id,
            comment=request.comment,
            query=request.query,
            answer=request.answer,
            sources=request.sources,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    return {"saved": True, "id": feedback_id, "message_id": message_id}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_user)])
def chat(request: ChatRequest, user=Depends(require_user)):
    if startup_error is not None:
        return ChatResponse(answer=f"Startup error: {startup_error}", conversation_id=0, sources=[])

    conversation_id = request.conversation_id
    is_new_conversation = conversation_id is None

    if conversation_id is None:
        conversation_id = create_conversation(
            user["id"],
            make_conversation_title(request.message),
        )
    elif not get_conversation(user["id"], conversation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    with ChatAdmission(user["id"], conversation_id):
        saved_messages = list_messages(user["id"], conversation_id)
        agent_messages = build_agent_messages(saved_messages)
        start = time.perf_counter()
        knowledge_preflight = build_knowledge_preflight(
            request.message,
            client,
            agent_messages,
            departments=user_knowledge_departments(user),
        )
        result = run_agent(
            client,
            agent_messages,
            request.message,
            knowledge_preflight=knowledge_preflight,
            return_sources=True,
        )
        answer = result["answer"]
        sources = result["sources"]
        add_knowledge_access_audit(
            user,
            "chat",
            request.message,
            sources,
            access_stats=knowledge_preflight.get("access_stats"),
        )
        log_event(
            logger,
            20,
            "chat_completed",
            user_id=user["id"],
            conversation_id=conversation_id,
            is_new_conversation=is_new_conversation,
            source_count=len(sources),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )

        save_chat_turn(
            user["id"],
            conversation_id,
            request.message,
            answer or "",
            sources=sources,
            title=make_conversation_title(request.message) if is_new_conversation else None,
        )

    return ChatResponse(answer=answer, conversation_id=conversation_id, sources=sources)


@app.post("/chat/stream", dependencies=[Depends(require_user)])
def chat_stream(request: ChatRequest, user=Depends(require_user)):
    if startup_error is not None:
        return StreamingResponse(
            iter([f"Startup error: {startup_error}"]),
            media_type="text/plain; charset=utf-8",
            headers={"X-Conversation-Id": "0"},
        )

    conversation_id = request.conversation_id
    is_new_conversation = conversation_id is None

    if conversation_id is None:
        conversation_id = create_conversation(
            user["id"],
            make_conversation_title(request.message),
        )
    elif not get_conversation(user["id"], conversation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    admission = ChatAdmission(user["id"], conversation_id)
    admission.__enter__()
    saved_messages = list_messages(user["id"], conversation_id)
    agent_messages = build_agent_messages(saved_messages)
    start = time.perf_counter()
    knowledge_preflight = build_knowledge_preflight(
        request.message,
        client,
        agent_messages,
        departments=user_knowledge_departments(user),
    )
    sources = knowledge_preflight["sources"]

    def stream_answer():
        answer_parts = []
        try:
            for chunk in run_agent_stream(
                client,
                agent_messages,
                request.message,
                knowledge_preflight=knowledge_preflight,
            ):
                answer_parts.append(chunk)
                yield chunk
        finally:
            answer = "".join(answer_parts)
            try:
                if answer:
                    add_knowledge_access_audit(
                        user,
                        "chat_stream",
                        request.message,
                        sources,
                        access_stats=knowledge_preflight.get("access_stats"),
                    )
                    save_chat_turn(
                        user["id"],
                        conversation_id,
                        request.message,
                        answer,
                        sources=sources,
                        title=make_conversation_title(request.message) if is_new_conversation else None,
                    )
                log_event(
                    logger,
                    20,
                    "chat_stream_completed",
                    user_id=user["id"],
                    conversation_id=conversation_id,
                    is_new_conversation=is_new_conversation,
                    source_count=len(sources),
                    answer_chars=len(answer),
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                )
            finally:
                admission.__exit__(None, None, None)

    return StreamingResponse(
        stream_answer(),
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Conversation-Id": str(conversation_id),
            "X-Knowledge-Sources": encode_sources_header(sources),
        },
    )


@app.get(
    "/billing/deepseek-balance",
    response_model=DeepSeekBalanceResponse,
    dependencies=[Depends(require_admin)],
)
def deepseek_balance():
    return get_deepseek_balance()


@app.get("/files", dependencies=[Depends(require_admin)])
def files():
    backend_dir = Path(__file__).resolve().parent
    names = sorted(path.name for path in backend_dir.iterdir() if path.is_file())
    return {"files": names}


@app.post("/knowledge/index-file", dependencies=[Depends(require_admin)])
def index_knowledge_file(request: IndexFileRequest, background_tasks: BackgroundTasks, user=Depends(require_admin)):
    target, error = knowledge.resolve_knowledge_file(request.path)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )
    normalized_metadata, error = knowledge.validate_document_metadata(request.metadata)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    resolved_document_id = request.document_id
    if resolved_document_id is None:
        resolved_document_id = knowledge.make_document_id(target, use_original_name=False)

    job_id = enqueue_index_job(
        background_tasks,
        path=request.path,
        document_id=resolved_document_id,
        notes=request.notes,
        category=request.category,
        tags=request.tags,
        use_original_name=False,
        metadata=normalized_metadata,
    )
    add_admin_audit_event(
        user,
        "knowledge.index_file",
        "knowledge_document",
        target_id=resolved_document_id,
        details={
            "job_id": job_id,
            "path": request.path,
            "category": request.category,
            "tags": request.tags or [],
        },
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=IndexJobResponse(
            job_id=job_id,
            status="queued",
            document_id=resolved_document_id,
            path=request.path,
            result=None,
            error=None,
        ).model_dump(),
    )


@app.post("/knowledge/upload", dependencies=[Depends(require_admin)])
def upload_knowledge_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    notes: str | None = Form(default=None),
    category: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    metadata: str | None = Form(default=None),
    user=Depends(require_admin),
):
    tag_list = parse_tags_field(tags)
    try:
        metadata_dict = parse_metadata_field(metadata)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    normalized_metadata, error = knowledge.validate_document_metadata(metadata_dict)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    try:
        target, error = knowledge.save_upload_file(file)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    relative_path = str(target.relative_to(knowledge.PROJECT_ROOT))
    document_id = target.name
    job_id = enqueue_index_job(
        background_tasks,
        path=relative_path,
        document_id=document_id,
        notes=notes,
        category=category,
        tags=tag_list,
        use_original_name=True,
        metadata=normalized_metadata,
    )
    add_admin_audit_event(
        user,
        "knowledge.upload",
        "knowledge_document",
        target_id=document_id,
        details={
            "job_id": job_id,
            "path": relative_path,
            "file_name": file.filename,
            "category": category,
            "tags": tag_list or [],
        },
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=IndexJobResponse(
            job_id=job_id,
            status="queued",
            document_id=document_id,
            path=relative_path,
            result=None,
            error=None,
        ).model_dump(),
    )


@app.get("/knowledge/index-jobs/{job_id}", response_model=IndexJobResponse, dependencies=[Depends(require_admin)])
def knowledge_index_job(job_id: str):
    job = get_index_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Index job not found.",
        )
    return IndexJobResponse(
        job_id=job["id"],
        status=job["status"],
        document_id=job.get("document_id"),
        path=job.get("path"),
        result=job.get("result"),
        error=job.get("error"),
    )


@app.get("/knowledge/documents", dependencies=[Depends(require_admin)])
def knowledge_documents():
    docs = vector_store.list_documents()
    # 为每个文档获取元数据
    enhanced_docs = []
    for doc in docs:
        doc_info = {"document_id": doc} if isinstance(doc, str) else doc
        doc_id = doc_info.get("document_id") or doc
        metadata = vector_store.get_document_metadata(doc_id)
        source_path = knowledge.source_path_from_metadata(doc_id, metadata)
        if metadata:
            doc_info["metadata"] = metadata
            doc_info["file_name"] = metadata.get("file_name") or doc_id
            doc_info["source_path"] = metadata.get("source_path")
            doc_info["file_ext"] = metadata.get("file_ext")
            doc_info["file_size"] = metadata.get("file_size")
            doc_info["category"] = metadata.get("category")
            doc_info["tags"] = metadata.get("tags") or []
            doc_info["indexed_at"] = metadata.get("indexed_at")
            doc_info["department"] = metadata.get("department")
            doc_info["doc_type"] = metadata.get("doc_type")
            doc_info["sensitivity"] = metadata.get("sensitivity")
            doc_info["version"] = metadata.get("version")
            doc_info["owner"] = metadata.get("owner")
            doc_info["effective_date"] = metadata.get("effective_date")
            doc_info["expiry_date"] = metadata.get("expiry_date")
        else:
            doc_info["file_name"] = doc_id
            doc_info["tags"] = []
        doc_info["source_exists"] = source_path is not None
        enhanced_docs.append(doc_info)
    
    return {"documents": enhanced_docs}


@app.delete("/knowledge/documents/{document_id}", dependencies=[Depends(require_admin)])
def delete_knowledge_document(document_id: str, user=Depends(require_admin)):
    metadata = vector_store.get_document_metadata(document_id)
    deleted_source_path = None
    vector_store.delete_document(document_id)
    try:
        deleted_source_path = knowledge.delete_uploaded_source_file(document_id, metadata)
    except OSError as error:
        log_event(
            logger,
            40,
            "knowledge_source_delete_failed",
            document_id=document_id,
            error=str(error),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Knowledge document was removed from indexes, but source file deletion failed: {error}",
        )
    result = {
        "deleted": True,
        "document_id": document_id,
        "source_deleted": deleted_source_path is not None,
        "source_path": deleted_source_path,
    }
    add_admin_audit_event(
        user,
        "knowledge.delete",
        "knowledge_document",
        target_id=document_id,
        details={
            "source_deleted": result["source_deleted"],
            "source_path": deleted_source_path,
        },
    )
    return result


@app.post("/knowledge/reindex", dependencies=[Depends(require_admin)])
def reindex_all_knowledge_documents(background_tasks: BackgroundTasks, user=Depends(require_admin)):
    queued_jobs = []
    skipped_documents = []

    for doc in vector_store.list_documents():
        doc_info = {"document_id": doc} if isinstance(doc, str) else doc
        document_id = doc_info.get("document_id")
        if not document_id:
            continue

        metadata = vector_store.get_document_metadata(document_id) or {}
        source_path = knowledge.source_path_from_metadata(document_id, metadata)
        if source_path is None:
            skipped_documents.append(document_id)
            continue

        try:
            relative_path = str(source_path.relative_to(knowledge.PROJECT_ROOT))
        except ValueError:
            relative_path = str(source_path)
        job_id = enqueue_index_job(
            background_tasks,
            path=relative_path,
            document_id=document_id,
            notes=metadata.get("user_notes"),
            category=metadata.get("category"),
            tags=metadata.get("tags") if isinstance(metadata.get("tags"), list) else None,
            use_original_name=True,
            metadata=metadata,
            force_reindex=True,
        )
        queued_jobs.append({
            "job_id": job_id,
            "document_id": document_id,
            "path": relative_path,
        })

    content = {
        "queued_count": len(queued_jobs),
        "skipped_count": len(skipped_documents),
        "jobs": queued_jobs,
        "skipped_documents": skipped_documents,
    }
    add_admin_audit_event(
        user,
        "knowledge.reindex_all",
        "knowledge_collection",
        details={
            "queued_count": content["queued_count"],
            "skipped_count": content["skipped_count"],
            "document_ids": [job["document_id"] for job in queued_jobs],
            "skipped_documents": skipped_documents,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=content,
    )


@app.get("/knowledge/sources", dependencies=[Depends(require_admin)])
def list_knowledge_sources():
    return {"sources": knowledge_sources.list_sources()}


@app.post("/knowledge/sources/{source_id}/sync", dependencies=[Depends(require_admin)])
def sync_knowledge_source(source_id: int, background_tasks: BackgroundTasks, user=Depends(require_admin)):
    def enqueue_source_index(**kwargs):
        return enqueue_index_job(background_tasks, **kwargs)

    result, error = knowledge_sources.sync_source(source_id, enqueue_source_index)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )
    add_admin_audit_event(
        user,
        "knowledge_source.sync",
        "knowledge_source",
        target_id=source_id,
        details={
            "queued_count": result.get("queued_count"),
            "unchanged_count": result.get("unchanged_count"),
            "missing_count": result.get("missing_count"),
            "skipped_count": result.get("skipped_count"),
            "removed_index_count": result.get("removed_index_count"),
        },
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=result,
    )


@app.delete("/knowledge/sources/missing-files", dependencies=[Depends(require_admin)])
def clear_missing_knowledge_source_files(user=Depends(require_admin)):
    deleted_count = delete_missing_knowledge_source_files()
    add_admin_audit_event(
        user,
        "knowledge_source.clear_missing_files",
        "knowledge_source_file",
        details={"deleted_count": deleted_count},
    )
    return {"deleted_count": deleted_count}


@app.post("/knowledge/documents/deduplicate", dependencies=[Depends(require_admin)])
def deduplicate_knowledge_documents(user=Depends(require_admin)):
    result = vector_store.deduplicate_documents_by_content_hash(
        reassign_document=reassign_knowledge_source_files,
    )
    add_admin_audit_event(
        user,
        "knowledge.deduplicate",
        "knowledge_document",
        details={
            "duplicate_group_count": result["duplicate_group_count"],
            "removed_count": result["removed_count"],
            "removed_documents": result["removed_documents"],
        },
    )
    return result


@app.get("/admin/knowledge-audit", dependencies=[Depends(require_admin)])
def admin_knowledge_audit(limit: int = 100):
    return {"audits": list_knowledge_access_audit(limit)}


@app.get("/admin/audit", dependencies=[Depends(require_admin)])
def admin_audit(limit: int = 100):
    return {"events": list_admin_audit_events(limit)}


@app.post("/knowledge/search")
def search_knowledge(request: SearchKnowledgeRequest, user=Depends(require_admin)):
    top_k = max(1, min(request.top_k, tools.MAX_KNOWLEDGE_RESULTS))
    start = time.perf_counter()
    retrieval_payload = search_knowledge_payload(
        request.query,
        top_k=top_k,
        min_score=request.min_score,
        category=request.category,
        tags=request.tags,
        file_extensions=request.file_extensions,
        departments=user_knowledge_departments(user),
    )
    kept_results = retrieval_payload["kept_results"]
    log_event(
        logger,
        20,
        "knowledge_search_completed",
        top_k=top_k,
        min_score=request.min_score,
        category=request.category,
        tags=request.tags or [],
        file_extensions=request.file_extensions or [],
        result_count=len(kept_results),
        duration_ms=round((time.perf_counter() - start) * 1000, 2),
    )

    result_sources = [search_result_to_source(result) for result in kept_results]
    add_knowledge_access_audit(
        user,
        "knowledge_search",
        request.query,
        result_sources,
        access_stats=retrieval_payload.get("access_stats"),
    )
    evidence_status = "supported" if len(result_sources) >= MIN_EVIDENCE_SOURCES else "insufficient"
    return {
        "results": result_sources,
        "evidence_status": evidence_status,
        "confidence": "high" if evidence_status == "supported" else "none",
        "access_stats": retrieval_payload.get("access_stats", {}),
    }
