"""Pydantic request / response schemas for all API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

# ──────────────────────── generic wrapper ────────────────────────


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ──────────────────────── conversation ────────────────────────


class CreateConversationRequest(BaseModel):
    user_id: int = 1
    title: str = ""


class ConversationBrief(BaseModel):
    id: int
    user_id: int
    title: str
    status: str
    current_phase: str | None = None
    message_count: int = 0
    estimated_cost: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageItem(BaseModel):
    id: int
    idx: int
    role: str
    content: str
    content_type: str | None = None
    estimated_cost: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    id: int
    user_id: int
    title: str
    status: str
    current_phase: str | None = None
    workspace_path: str
    estimated_cost: float | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageItem] = []
    outlines: list["OutlineBrief"] = []
    presentations: list["PresentationBrief"] = []

    model_config = {"from_attributes": True}


# ──────────────────────── chat ────────────────────────


class ChatSendRequest(BaseModel):
    user_id: int = 1
    conversation_id: int
    message: str


# ──────────────────────── outline ────────────────────────


class OutlineSlideItem(BaseModel):
    id: int
    slide_index: int
    title: str
    content_json: dict | None = None
    layout_type: str | None = None
    has_image: bool | None = None
    has_chart: bool | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class OutlineBrief(BaseModel):
    id: int
    user_id: int
    conversation_id: int
    title: str
    status: str
    eval_score: float | None = None
    version: int
    slide_count: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OutlineDetail(OutlineBrief):
    slides: list[OutlineSlideItem] = []


# ──────────────────────── ppt ────────────────────────


class PresentationBrief(BaseModel):
    id: int
    user_id: int
    conversation_id: int
    outline_id: int | None = None
    status: str
    slide_count: int | None = None
    file_path: str
    file_size: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PresentationDetail(PresentationBrief):
    template_id: int | None = None
    template_name: str | None = None
    color_scheme_id: int | None = None
    color_scheme_name: str | None = None
    error_msg: str | None = None


class PresentationSlideDetail(BaseModel):
    id: int
    slide_index: int
    layout_name: str
    outline_slide_id: int | None = None
    template_id: int | None = None
    color_scheme_id: int | None = None
    status: str | None = None
    retry_count: int | None = None
    agent_outputs: dict | None = None
    chart_data: dict | None = None
    table_data: dict | None = None
    image_paths: dict | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class PresentationSlidesResponse(BaseModel):
    presentation_id: int
    slides: list[PresentationSlideDetail]


# ──────────────────────── snapshot ────────────────────────


class SnapshotBrief(BaseModel):
    id: int
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SnapshotDetail(BaseModel):
    id: int
    presentation_id: int
    user_id: int
    conversation_id: int
    version: int
    outline_json: dict
    presentation_json: dict
    created_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────────── cost ────────────────────────


class CostSummaryData(BaseModel):
    user_id: int
    total_cost: float
    total_conversations: int
    total_messages: int
    avg_cost_per_conversation: float
    avg_cost_per_day: float
    days: int


class CostByDateItem(BaseModel):
    date: str
    cost: float
    conversations: int
    messages: int


class CostByConversationItem(BaseModel):
    conversation_id: int
    title: str
    cost: float
    message_count: int
    created_at: datetime
    updated_at: datetime


# ──────────────────────── knowledge ────────────────────────


class KnowledgeFileItem(BaseModel):
    id: int
    user_id: int
    conversation_id: int | None = None  # derived from file_path
    filename: str
    file_type: str
    file_size: int | None = None
    chunk_count: int | None = None
    source_type: str | None = None
    status: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeUploadedFile(BaseModel):
    id: int | None = None  # None for images (saved to input/ dir, not knowledge DB)
    conversation_id: int | None = None
    filename: str
    file_type: str
    file_size: int | None = None
    chunk_count: int | None = None
    status: str | None = None


class KnowledgeUploadResult(BaseModel):
    uploaded: list[KnowledgeUploadedFile] = []
    failed: list[dict] = []


class KnowledgeFilesSummary(BaseModel):
    total_files: int
    total_size: int
    total_chunks: int


class KnowledgeFilesListData(BaseModel):
    items: list[KnowledgeFileItem]
    total: int
    summary: KnowledgeFilesSummary


# ──────────────────────── workspace ────────────────────────


class WorkspaceConvStatus(BaseModel):
    conversation_id: int
    disk_usage: str
    file_counts: dict[str, int]


class BM25IndexInfo(BaseModel):
    user_id: int
    file: str
    chunk_count: int


class BM25Status(BaseModel):
    index_dir: str
    indexes: list[BM25IndexInfo]


class WorkspaceStatusData(BaseModel):
    workspace_root: str
    conversations: list[WorkspaceConvStatus]
    bm25_index: BM25Status


# ──────────────────────── system ────────────────────────


class ConfigData(BaseModel):
    rag: dict
    agent: dict
    llm: dict
    web_search: dict


class HealthData(BaseModel):
    status: str
    db: str = "unknown"
    llm: str = "unknown"
    bm25: str = "unknown"


# ──────────────────────── auth ────────────────────────


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=256)


class LoginRequest(BaseModel):
    name: str
    password: str


class AuthTokenData(BaseModel):
    token: str
    user_id: int
    name: str


# ──────────────────────── sse events (not for API, for doc) ────────────────────────


class SSEPhaseEvent(BaseModel):
    phase: str
    message: str


class SSEProgressEvent(BaseModel):
    step: str
    detail: str
    pct: float


class SSEOutlineEvent(BaseModel):
    outline_id: int
    title: str
    slides: list[dict]
    eval_score: float | None = None


class SSEKnowledgeEvent(BaseModel):
    sources: list[dict]


class SSEPptReadyEvent(BaseModel):
    presentation_id: int
    file_path: str
    slide_count: int
    download_url: str


class SSEDoneEvent(BaseModel):
    estimated_cost: float
    elapsed_seconds: float


class SSEErrorEvent(BaseModel):
    code: int
    message: str
    retryable: bool = False


# reveal forward references
ConversationDetail.model_rebuild()
