# -*- coding: utf-8 -*-

import time

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

import app_state
from config import (
    LOGIN_LOCKOUT_SECONDS,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE_SECONDS,
)
from database import authenticate_user, delete_session
from dependencies import (
    clear_expired_login_failures,
    clear_login_failures,
    create_session,
    get_client_ip,
    get_session_username,
    is_login_locked,
    login_failure_key,
    record_login_failure,
    require_auth_config,
)
from schemas import AuthResponse, LoginRequest


router = APIRouter()


@router.post("/login", response_model=AuthResponse)
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
        key=app_state.SESSION_COOKIE,
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


@router.post("/logout", response_model=AuthResponse)
def logout(response: Response, agent_session: str | None = Cookie(default=None, alias=app_state.SESSION_COOKIE)):
    if agent_session:
        delete_session(agent_session)

    response.delete_cookie(
        key=app_state.SESSION_COOKIE,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE,
    )
    return AuthResponse(authenticated=False)


@router.get("/me", response_model=AuthResponse)
def me(agent_session: str | None = Cookie(default=None, alias=app_state.SESSION_COOKIE)):
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
