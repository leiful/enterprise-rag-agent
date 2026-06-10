# -*- coding: utf-8 -*-

import secrets
import time

from fastapi import Cookie, Depends, HTTPException, Request, status

import app_state
from app_logging import get_logger, log_event
from config import (
    APP_PASSWORD as CONFIG_APP_PASSWORD,
    APP_USERNAME as CONFIG_APP_USERNAME,
    LOGIN_LOCKOUT_SECONDS,
    LOGIN_MAX_FAILED_ATTEMPTS,
    SESSION_MAX_AGE_SECONDS,
)
from database import create_session as save_session, get_session


APP_USERNAME = CONFIG_APP_USERNAME
APP_PASSWORD = CONFIG_APP_PASSWORD
login_failures = {}
logger = get_logger("backend.auth")


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


def require_user(agent_session: str | None = Cookie(default=None, alias=app_state.SESSION_COOKIE)):
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
