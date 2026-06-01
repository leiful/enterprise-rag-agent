# -*- coding: utf-8 -*-

from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import time

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from AI_agent import create_client, run_agent
from config import APP_PASSWORD, APP_USERNAME, SESSION_MAX_AGE_SECONDS
from database import authenticate_user, create_session as save_session, delete_session, get_session, init_db
from memory import load_messages, save_messages


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    authenticated: bool
    username: str | None = None


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str


client = None
messages = None
startup_error = None
SESSION_COOKIE = "agent_session"


def startup():
    global client, messages, startup_error
    init_db()
    messages = load_messages()

    try:
        client = create_client()
        startup_error = None
    except RuntimeError as error:
        startup_error = str(error)


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

    return session["username"]


def require_user(agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if not agent_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login required.",
        )

    username = get_session_username(agent_session)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session.",
        )

    return username


app = FastAPI(title="AI Tool Calling Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok" if startup_error is None else "missing_api_key",
        "error": startup_error,
    }


@app.post("/login", response_model=AuthResponse)
def login(request: LoginRequest, response: Response):
    require_auth_config()

    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session(user["id"]),
        httponly=True,
        max_age=SESSION_MAX_AGE_SECONDS,
        samesite="lax",
    )
    return AuthResponse(authenticated=True, username=request.username)


@app.post("/logout", response_model=AuthResponse)
def logout(response: Response, agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if agent_session:
        delete_session(agent_session)

    response.delete_cookie(key=SESSION_COOKIE)
    return AuthResponse(authenticated=False)


@app.get("/me", response_model=AuthResponse)
def me(agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if not agent_session:
        return AuthResponse(authenticated=False)

    username = get_session_username(agent_session)
    if username is None:
        return AuthResponse(authenticated=False)

    return AuthResponse(authenticated=True, username=username)


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_user)])
def chat(request: ChatRequest):
    if startup_error is not None:
        return ChatResponse(answer=f"Startup error: {startup_error}")

    answer = run_agent(client, messages, request.message)
    save_messages(messages)
    return ChatResponse(answer=answer)


@app.get("/files", dependencies=[Depends(require_user)])
def files():
    backend_dir = Path(__file__).resolve().parent
    names = sorted(path.name for path in backend_dir.iterdir() if path.is_file())
    return {"files": names}
