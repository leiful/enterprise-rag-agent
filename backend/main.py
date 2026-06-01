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
from config import SYSTEM_MESSAGE
from database import (
    add_message,
    authenticate_user,
    create_conversation,
    create_session as save_session,
    delete_session,
    get_conversation,
    get_session,
    init_db,
    list_conversations,
    list_messages,
    touch_conversation,
    update_conversation_title,
)


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    authenticated: bool
    username: str | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    answer: str
    conversation_id: int


class ConversationRequest(BaseModel):
    title: str | None = None


client = None
startup_error = None
SESSION_COOKIE = "agent_session"


def startup():
    global client, startup_error
    init_db()

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

    return {"id": session["user_id"], "username": session["username"]}


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

    user = get_session_username(agent_session)
    if user is None:
        return AuthResponse(authenticated=False)

    return AuthResponse(authenticated=True, username=user["username"])


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


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_user)])
def chat(request: ChatRequest, user=Depends(require_user)):
    if startup_error is not None:
        return ChatResponse(answer=f"Startup error: {startup_error}", conversation_id=0)

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

    saved_messages = list_messages(user["id"], conversation_id)
    agent_messages = build_agent_messages(saved_messages)
    answer = run_agent(client, agent_messages, request.message)

    add_message(conversation_id, "user", request.message)
    add_message(conversation_id, "assistant", answer or "")
    touch_conversation(user["id"], conversation_id)

    if is_new_conversation:
        update_conversation_title(
            user["id"],
            conversation_id,
            make_conversation_title(request.message),
        )

    return ChatResponse(answer=answer, conversation_id=conversation_id)


@app.get("/files", dependencies=[Depends(require_user)])
def files():
    backend_dir = Path(__file__).resolve().parent
    names = sorted(path.name for path in backend_dir.iterdir() if path.is_file())
    return {"files": names}
