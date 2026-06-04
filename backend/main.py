# -*- coding: utf-8 -*-

from contextlib import asynccontextmanager
import base64
import json
import os
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from AI_agent import build_knowledge_preflight, create_client, run_agent, run_agent_stream
from config import APP_PASSWORD, APP_USERNAME, BASE_URL, SESSION_MAX_AGE_SECONDS
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
import knowledge
import tools
import vector_store


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
    sources: list[dict] = Field(default_factory=list)


class ConversationRequest(BaseModel):
    title: str | None = None


class IndexFileRequest(BaseModel):
    path: str
    document_id: str | None = None
    notes: str | None = None


class SearchKnowledgeRequest(BaseModel):
    query: str
    top_k: int = 3
    min_score: float = 0.3


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
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):517[0-9]",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-Id", "X-Knowledge-Sources"],
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


def encode_sources_header(sources):
    sources_json = json.dumps(sources or [], ensure_ascii=False)
    return base64.b64encode(sources_json.encode("utf-8")).decode("ascii")


def get_deepseek_balance():
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEEPSEEK_API_KEY is not configured.",
        )

    request = Request(
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

    saved_messages = list_messages(user["id"], conversation_id)
    agent_messages = build_agent_messages(saved_messages)
    result = run_agent(client, agent_messages, request.message, return_sources=True)
    answer = result["answer"]
    sources = result["sources"]

    add_message(conversation_id, "user", request.message)
    add_message(conversation_id, "assistant", answer or "", sources=sources)
    touch_conversation(user["id"], conversation_id)

    if is_new_conversation:
        update_conversation_title(
            user["id"],
            conversation_id,
            make_conversation_title(request.message),
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

    saved_messages = list_messages(user["id"], conversation_id)
    agent_messages = build_agent_messages(saved_messages)
    knowledge_preflight = build_knowledge_preflight(request.message, client, agent_messages)
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
            add_message(conversation_id, "user", request.message)
            add_message(conversation_id, "assistant", answer, sources=sources)
            touch_conversation(user["id"], conversation_id)

            if is_new_conversation:
                update_conversation_title(
                    user["id"],
                    conversation_id,
                    make_conversation_title(request.message),
                )

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
    dependencies=[Depends(require_user)],
)
def deepseek_balance():
    return get_deepseek_balance()


@app.get("/files", dependencies=[Depends(require_user)])
def files():
    backend_dir = Path(__file__).resolve().parent
    names = sorted(path.name for path in backend_dir.iterdir() if path.is_file())
    return {"files": names}


@app.post("/knowledge/index-file", dependencies=[Depends(require_user)])
def index_knowledge_file(request: IndexFileRequest):
    try:
        result, error = knowledge.index_file(
            request.path,
            request.document_id,
            notes=request.notes,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding service failed: {error}",
        )

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return result


@app.post("/knowledge/upload", dependencies=[Depends(require_user)])
def upload_knowledge_file(
    file: UploadFile = File(...),
    notes: str | None = Form(default=None),
):
    try:
        result, error = knowledge.upload_and_index_file(file, notes=notes)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding service failed: {error}",
        )

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return result


@app.get("/knowledge/documents", dependencies=[Depends(require_user)])
def knowledge_documents():
    return {"documents": vector_store.list_documents()}


@app.delete("/knowledge/documents/{document_id}", dependencies=[Depends(require_user)])
def delete_knowledge_document(document_id: str):
    vector_store.delete_document(document_id)
    return {"deleted": True, "document_id": document_id}


@app.post("/knowledge/search", dependencies=[Depends(require_user)])
def search_knowledge(request: SearchKnowledgeRequest):
    top_k = max(1, min(request.top_k, tools.MAX_KNOWLEDGE_RESULTS))
    results = vector_store.search(request.query, top_k=top_k)
    kept_results = [
        result for result in results
        if result.score >= request.min_score
    ]

    return {
        "results": [
            {
                "score": result.score,
                "chunk_id": result.chunk_id,
                "document_id": result.document_id,
                "chunk_index": result.chunk_index,
                "text": result.text,
            }
            for result in kept_results
        ]
    }
