# -*- coding: utf-8 -*-

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from AI_agent import create_client, run_agent
from config import APP_API_KEY
from memory import load_messages, save_messages


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str


client = None
messages = None
startup_error = None
API_KEY_HEADER = "X-API-Key"


def startup():
    global client, messages, startup_error
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


def require_api_key(x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER)):
    if not APP_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APP_API_KEY is not configured.",
        )

    if x_api_key != APP_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )


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


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(request: ChatRequest):
    if startup_error is not None:
        return ChatResponse(answer=f"Startup error: {startup_error}")

    answer = run_agent(client, messages, request.message)
    save_messages(messages)
    return ChatResponse(answer=answer)


@app.get("/files", dependencies=[Depends(require_api_key)])
def files():
    backend_dir = Path(__file__).resolve().parent
    names = sorted(path.name for path in backend_dir.iterdir() if path.is_file())
    return {"files": names}
