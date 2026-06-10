# -*- coding: utf-8 -*-

from pydantic import BaseModel, Field

from config import DEFAULT_KNOWLEDGE_MIN_SCORE, DEFAULT_KNOWLEDGE_TOP_K


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
    skip_search: bool = False


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
    acknowledged_at: str | None = None


class AcknowledgeIndexJobsRequest(BaseModel):
    job_ids: list[str] | None = None


class BalanceInfo(BaseModel):
    currency: str
    total_balance: str
    granted_balance: str
    topped_up_balance: str


class DeepSeekBalanceResponse(BaseModel):
    is_available: bool
    balance_infos: list[BalanceInfo]
