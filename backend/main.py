# -*- coding: utf-8 -*-

from contextlib import asynccontextmanager
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_logging import configure_logging, get_logger, log_event, new_request_id, reset_request_id, set_request_id
from AI_agent import create_client
import app_state
import dependencies as auth_dependencies
from config import (
    APP_ENV,
    APP_PASSWORD,
    APP_USERNAME,
    SESSION_MAX_AGE_SECONDS,
    cors_allowed_origins,
    cors_allow_origin_regex,
)
from config import validate_runtime_config
from database import (
    backfill_model_usage_scopes,
    close_pool,
    create_session as save_session,
    init_db,
)
import knowledge
import knowledge_sources
from dependencies import create_session
from routes import admin, auth, chat, operations
from routes.operations import get_database_health


login_failures = auth_dependencies.login_failures
logger = get_logger("backend.main")

SESSION_COOKIE = app_state.SESSION_COOKIE
ChatAdmission = app_state.ChatAdmission
current_chat_admission_status = app_state.current_chat_admission_status
chat_admission_lock = app_state.chat_admission_lock
active_chat_by_user = app_state.active_chat_by_user
active_chat_by_conversation = app_state.active_chat_by_conversation
latest_rag_eval_report = operations.latest_rag_eval_report
get_rag_operational_status = operations.get_rag_operational_status
run_rag_eval_suite = operations.run_rag_eval_suite
rag_eval_suite_list = operations.rag_eval_suite_list


def startup():
    configure_logging()
    app_state.config_issues = validate_runtime_config()

    try:
        init_db()
        backfill_model_usage_scopes()
        knowledge_sources.ensure_default_local_source()
    except Exception as error:
        app_state.startup_error = str(error)
        log_event(
            logger,
            40,
            "app_startup_db_failed",
            error=str(error),
        )
        return

    try:
        app_state.client = create_client()
        app_state.startup_error = None
        log_event(
            logger,
            20,
            "app_startup_completed",
            config_error_count=sum(1 for issue in app_state.config_issues if issue["severity"] == "error"),
            config_warning_count=sum(1 for issue in app_state.config_issues if issue["severity"] == "warning"),
        )
    except RuntimeError as error:
        app_state.startup_error = str(error)
        log_event(
            logger,
            40,
            "app_startup_model_client_failed",
            error=str(error),
            config_error_count=sum(1 for issue in app_state.config_issues if issue["severity"] == "error"),
            config_warning_count=sum(1 for issue in app_state.config_issues if issue["severity"] == "warning"),
        )


@asynccontextmanager
async def lifespan(app):
    startup()
    yield
    close_pool()


def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")


app = FastAPI(
    title="AI Tool Calling Agent",
    lifespan=lifespan,
    docs_url=None if APP_ENV == "production" else "/docs",
    redoc_url=None if APP_ENV == "production" else "/redoc",
    openapi_url=None if APP_ENV == "production" else "/openapi.json",
)

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


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(operations.router)


@app.get("/health")
def health():
    has_config_errors = any(issue["severity"] == "error" for issue in app_state.config_issues)
    has_config_warnings = any(issue["severity"] == "warning" for issue in app_state.config_issues)
    database_health = get_database_health()
    model_status = "ok" if app_state.startup_error is None else "error"
    config_status = "error" if has_config_errors else "warning" if has_config_warnings else "ok"
    overall_status = "ok"
    if app_state.startup_error is not None or has_config_errors or database_health["status"] == "error":
        overall_status = "error"
    elif has_config_warnings:
        overall_status = "degraded"

    return {
        "status": overall_status,
        "error": app_state.startup_error,
        "checks": {
            "config": {
                "status": config_status,
                "issues": app_state.config_issues,
            },
            "database": database_health,
            "model_client": {
                "status": model_status,
                "error": app_state.startup_error,
            },
        },
    }
