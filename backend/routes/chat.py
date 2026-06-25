# -*- coding: utf-8 -*-

import base64
import json
import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

import app_state
from AI_agent import run_agent, run_agent_stream_with_preflight
from app_logging import get_logger, log_event

from database import (
    add_knowledge_access_audit,
    add_rag_feedback,
    create_conversation,
    find_feedback_message_id,
    get_conversation,
    list_conversations,
    list_messages,
    save_chat_turn,
)
from dependencies import require_user, user_knowledge_departments
import model_usage
from schemas import ChatRequest, ChatResponse, ConversationRequest, FeedbackRequest


router = APIRouter()
logger = get_logger("backend.chat")


def make_conversation_title(message):
    title = " ".join(message.split())
    if len(title) > 48:
        return f"{title[:45]}..."
    return title or "New conversation"


def encode_sources_header(sources):
    compact_sources = []
    for source in sources or []:
        metadata = source.get("metadata") if isinstance(source, dict) else {}
        compact_sources.append(
            {
                "label": source.get("label"),
                "document_id": source.get("document_id"),
                "chunk_id": source.get("chunk_id"),
                "chunk_index": source.get("chunk_index"),
                "score": source.get("score"),
                "text": (source.get("text") or "")[:280],
                "page_start": source.get("page_start"),
                "page_end": source.get("page_end"),
                "department": (metadata or {}).get("department"),
            }
        )
    sources_json = json.dumps(compact_sources, ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(sources_json.encode("utf-8")).decode("ascii")


@router.get("/conversations", dependencies=[Depends(require_user)])
def conversations(user=Depends(require_user)):
    return {"conversations": list_conversations(user["id"])}


@router.post("/conversations", dependencies=[Depends(require_user)])
def new_conversation(request: ConversationRequest, user=Depends(require_user)):
    title = request.title or "New conversation"
    conversation_id = create_conversation(user["id"], title)
    return {
        "id": conversation_id,
        "title": title,
    }


@router.get("/conversations/{conversation_id}/messages", dependencies=[Depends(require_user)])
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


@router.post("/feedback", dependencies=[Depends(require_user)])
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


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_user)])
def chat(request: ChatRequest, user=Depends(require_user)):
    if app_state.startup_error is not None:
        return ChatResponse(answer=f"Startup error: {app_state.startup_error}", conversation_id=0, sources=[])

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

    scope_token = model_usage.set_usage_scope("chat")
    try:
        with app_state.ChatAdmission(user["id"], conversation_id):
            start = time.perf_counter()
            result = run_agent(
                app_state.client,
                None,
                request.message,
                return_sources=True,
                departments=user_knowledge_departments(user),
                thread_id=conversation_id,
                user_id=user["id"],
            )
            answer = result["answer"]
            sources = result["sources"]
            access_stats = (result.get("knowledge_preflight") or {}).get("access_stats")
            add_knowledge_access_audit(user, "chat", request.message, sources, access_stats=access_stats)
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
    finally:
        model_usage.reset_usage_scope(scope_token)

    return ChatResponse(answer=answer, conversation_id=conversation_id, sources=sources)


@router.post("/chat/stream", dependencies=[Depends(require_user)])
def chat_stream(request: ChatRequest, user=Depends(require_user)):
    if app_state.startup_error is not None:
        return StreamingResponse(
            iter([f"Startup error: {app_state.startup_error}"]),
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

    admission = app_state.ChatAdmission(user["id"], conversation_id)
    admission.__enter__()
    start = time.perf_counter()
    answer_iter, sources = run_agent_stream_with_preflight(
        app_state.client,
        None,
        request.message,
        departments=user_knowledge_departments(user),
        thread_id=conversation_id,
        user_id=user["id"],
    )

    def stream_answer():
        answer_parts = []
        scope_token = model_usage.set_usage_scope("chat")
        try:
            for chunk in answer_iter:
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
                        access_stats=None,
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
                model_usage.reset_usage_scope(scope_token)

    return StreamingResponse(
        stream_answer(),
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Conversation-Id": str(conversation_id),
            "X-Knowledge-Sources": encode_sources_header(sources),
        },
    )
